"""A company's own outgoing mail service for Dejoiy Mail.

A company admin enters the SMTP details of the service they already pay for (Amazon SES, Resend,
Brevo, Mailgun, Postmark, their own server: every one of them speaks SMTP). From then on mail that
people in that company (or only in the chosen departments) send to addresses outside the company
goes out through that service instead of Dejoiy Mail's own server, so it carries the company's
sending reputation. The copy still lands in the sender's Sent folder.

Stands alone (standard library only). Wiring it in:
    relays = Relays(state_dir / 'relays.json', key_file=state_dir / 'relay.key')
    relays.action(op, payload, domain, me)      # from the admin action handler
    cfg = relays.route(domain, department, recipients, local)   # None -> send the usual way
    send(cfg, sender, recipients, message)      # raises RelayError with what the service said

The password is kept encrypted (key in a separate file, both readable by the mail app only) and is
never sent back to the browser. Someone with root on the server can still read it.
"""
import hashlib, hmac, json, os, re, secrets, smtplib, socket, ssl, threading, ipaddress
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, formataddr
from pathlib import Path

PORTS = (465, 587, 2465, 2587, 25)
SECURITY = ('starttls', 'ssl')
DOMAIN = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')
ADDRESS = re.compile(r'^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$')


class RelayError(ValueError):
    """Something the admin or the sender can act on; the message is safe to show."""


# ---- keeping the password ----
def _stream(key, nonce, n):
    out = b''; i = 0
    while len(out) < n:
        out += hmac.new(key, nonce + i.to_bytes(8, 'big'), hashlib.sha256).digest(); i += 1
    return out[:n]

def seal(key, text):
    """Encrypts text with a 32-byte key: HMAC-SHA256 in counter mode, then a tag over nonce and ciphertext."""
    enc, mac = hashlib.sha256(b'enc' + key).digest(), hashlib.sha256(b'mac' + key).digest()
    nonce = secrets.token_bytes(16); raw = text.encode()
    body = bytes(a ^ b for a, b in zip(raw, _stream(enc, nonce, len(raw))))
    return (nonce + body + hmac.new(mac, nonce + body, hashlib.sha256).digest()).hex()

def unseal(key, sealed):
    """The text back, or RelayError when it was changed or the key is not the one that sealed it."""
    try: blob = bytes.fromhex(sealed)
    except (ValueError, TypeError): raise RelayError('The saved password cannot be read. Enter it again.')
    if len(blob) < 48: raise RelayError('The saved password cannot be read. Enter it again.')
    enc, mac = hashlib.sha256(b'enc' + key).digest(), hashlib.sha256(b'mac' + key).digest()
    nonce, body, tag = blob[:16], blob[16:-32], blob[-32:]
    if not hmac.compare_digest(tag, hmac.new(mac, nonce + body, hashlib.sha256).digest()):
        raise RelayError('The saved password cannot be read. Enter it again.')
    return bytes(a ^ b for a, b in zip(body, _stream(enc, nonce, len(body)))).decode()


def public_host(host):
    """True when every address of this host is on the public internet (never connect into our own network)."""
    try: found = {info[4][0] for info in socket.getaddrinfo(host, 587, type=socket.SOCK_STREAM)}
    except OSError: return False
    return bool(found) and all(ipaddress.ip_address(a.split('%')[0]).is_global for a in found)


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', str(text or '').lower()).strip('-')[:60]


class Relays:
    def __init__(self, path, key_file=None, key=None, is_public=public_host, deliver=None):
        self.path, self.is_public, self.deliver = Path(path), is_public, deliver or send
        self.lock = threading.Lock()
        if key is None:
            key_file = Path(key_file)
            if not key_file.exists():
                fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as handle: handle.write(secrets.token_bytes(32))
            key = key_file.read_bytes()
        if len(key) < 32: raise ValueError('The relay key must be at least 32 bytes.')
        self.key = key
        try: self.all = json.loads(self.path.read_text())
        except (OSError, ValueError): self.all = {}

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle: json.dump(self.all, handle)
        os.replace(tmp, self.path)

    @staticmethod
    def public(cfg):
        """What the admin page may see: everything but the password."""
        if not cfg: return {'configured': False}
        return {'configured': True, **{k: cfg[k] for k in ('host', 'port', 'security', 'user', 'departments', 'active', 'last')}}

    def clean(self, payload, old):
        host = str(payload.get('host') or '').strip().lower().rstrip('.')
        if not DOMAIN.fullmatch(host) or len(host) > 253: raise RelayError('Enter the SMTP server name, like email-smtp.ap-south-1.amazonaws.com or smtp.resend.com.')
        port = payload.get('port')
        if isinstance(port, bool) or not isinstance(port, int) or port not in PORTS: raise RelayError('Use port 587 or 465 (2587, 2465 and 25 also work).')
        security = payload.get('security')
        if security not in SECURITY: raise RelayError('Choose STARTTLS (port 587) or SSL (port 465).')
        user = str(payload.get('user') or '').strip()
        if not user or len(user) > 320 or any(ord(c) < 32 for c in user): raise RelayError('Enter the SMTP user name your mail service gave you.')
        password = payload.get('password')
        if password:
            if not isinstance(password, str) or len(password) > 1024 or any(ord(c) < 32 for c in password): raise RelayError('Enter the SMTP password or API key your mail service gave you.')
            sealed = seal(self.key, password)
        elif old and old.get('host') == host and old.get('user') == user: sealed = old['password']   # unchanged: keep the saved one
        else: raise RelayError('Enter the SMTP password or API key.')
        departments = payload.get('departments') or []
        if not isinstance(departments, list) or len(departments) > 50 or any(not isinstance(d, str) or not slug(d) for d in departments):
            raise RelayError('Choose departments from the list.')
        if not self.is_public(host): raise RelayError('That server is not reachable on the public internet.')
        return {'host': host, 'port': port, 'security': security, 'user': user, 'password': sealed,
                'departments': sorted({d.strip()[:120] for d in departments}), 'active': payload.get('active', True) is not False,
                'last': old.get('last') if old else None}

    def action(self, op, payload, domain, me=''):
        """One admin request for one company's domain. Returns what the page should show."""
        domain = str(domain or '').strip().lower()
        if not DOMAIN.fullmatch(domain): raise RelayError('Choose a domain first.')
        payload = payload if isinstance(payload, dict) else {}
        if op == 'relay_test': return self.test(domain, me)
        with self.lock:
            if op == 'relay_set': self.all[domain] = self.clean(payload, self.all.get(domain)); self.save()
            elif op == 'relay_remove': self.all.pop(domain, None); self.save()
            elif op != 'relay_get': raise RelayError('Unknown action.')
            return {'domain': domain, 'relay': self.public(self.all.get(domain))}

    def config(self, domain):
        """The company's service with the password opened, or None."""
        with self.lock: cfg = dict(self.all.get(domain) or {})
        if not cfg: return None
        cfg['password'] = unseal(self.key, cfg['password'])
        return cfg

    def route(self, domain, department, recipients, local=()):
        """The service this mail goes out through, or None for the usual way.
        Used when the company has an active one, the sender is in a chosen department (or none were chosen),
        and at least one recipient is outside the mail server's own domains."""
        with self.lock: cfg = self.all.get(domain)
        if not cfg or not cfg.get('active'): return None
        if cfg['departments'] and slug(department) not in {slug(d) for d in cfg['departments']}: return None
        inside = {d.lower() for d in local} | {domain}
        if all(r.rsplit('@', 1)[-1].lower() in inside for r in recipients): return None
        return self.config(domain)

    def record(self, domain, ok, note):
        with self.lock:
            if domain in self.all:
                import time
                self.all[domain]['last'] = {'at': int(time.time()), 'ok': ok, 'note': str(note)[:200]}; self.save()

    def test(self, domain, me):
        """Sends one real mail through the company's service to the admin's own address and reports the answer."""
        cfg = self.config(domain)
        if not cfg: raise RelayError('Save the mail service first.')
        if not ADDRESS.fullmatch(me or '') or me.rsplit('@', 1)[1].lower() != domain: raise RelayError('The test goes to your own ' + domain + ' address.')
        msg = build(me, '', [me], [], 'Dejoiy Mail test: your mail service works',
                    'This test went out through ' + cfg['host'] + '.\nMail from ' + domain + ' to outside addresses now uses it.', None, [])
        try: self.deliver(cfg, me, [me], msg)
        except RelayError as e:
            self.record(domain, False, str(e)); raise
        self.record(domain, True, 'Test mail accepted')
        with self.lock: return {'domain': domain, 'relay': self.public(self.all.get(domain)), 'sent': True}


def build(sender, name, to, cc, subject, text, html, attachments, in_reply_to='', important=False):
    """The mail as it goes on the wire. attachments: [(bytes, filename, 'type/subtype')]. Bcc is never a header."""
    msg = EmailMessage()
    msg['From'] = formataddr((name, sender)) if name else sender
    if to: msg['To'] = ', '.join(to)
    if cc: msg['Cc'] = ', '.join(cc)
    msg['Subject'] = re.sub(r'[\r\n]+', ' ', str(subject or ''))[:900]
    msg['Date'] = formatdate(localtime=True); msg['Message-ID'] = make_msgid(domain=sender.rsplit('@', 1)[1])
    if in_reply_to: msg['In-Reply-To'] = in_reply_to; msg['References'] = in_reply_to
    if important: msg['X-Priority'] = '1'; msg['Importance'] = 'high'
    msg.set_content(text or '')
    if html: msg.add_alternative(html, subtype='html')
    for raw, filename, mime in attachments:
        main, _, sub = (mime or 'application/octet-stream').partition('/')
        msg.add_attachment(raw, maintype=main or 'application', subtype=sub or 'octet-stream', filename=filename)
    return msg


def send(cfg, sender, recipients, msg, timeout=30):
    """Hands the mail to the company's service. Raises RelayError with the service's own answer when it says no."""
    context = ssl.create_default_context()
    try:
        if cfg['security'] == 'ssl': server = smtplib.SMTP_SSL(cfg['host'], cfg['port'], timeout=timeout, context=context)
        else:
            server = smtplib.SMTP(cfg['host'], cfg['port'], timeout=timeout); server.starttls(context=context)   # never sends the password in the clear
        with server:
            server.login(cfg['user'], cfg['password'])
            refused = server.send_message(msg, from_addr=sender, to_addrs=list(recipients))
        if refused: raise RelayError('Your mail service refused: ' + ', '.join(sorted(refused))[:300])
    except smtplib.SMTPAuthenticationError: raise RelayError('Your mail service did not accept the user name and password.')
    except smtplib.SMTPSenderRefused as e: raise RelayError(f'Your mail service does not let {sender} send yet (verify the domain or address there): ' + _said(e.smtp_error))
    except smtplib.SMTPRecipientsRefused as e: raise RelayError('Your mail service refused the recipients: ' + ', '.join(sorted(e.recipients))[:300])
    except smtplib.SMTPResponseException as e: raise RelayError('Your mail service answered: ' + _said(e.smtp_error))
    except (smtplib.SMTPException, ssl.SSLError, OSError) as e: raise RelayError('Could not reach your mail service (' + (str(e) or type(e).__name__)[:160] + ').')

def _said(raw):
    return (raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else str(raw))[:240]
