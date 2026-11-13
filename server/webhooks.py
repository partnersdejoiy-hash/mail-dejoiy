"""Webhooks for Dejoiy Mail: tell a company's own tools when something happens.

A company admin gives an https address and picks events. When one happens, a small signed
JSON note is posted there, so n8n, Zapier, Make or the company's own code can react.
The note says who, what and when. It never carries mail content, passwords or sessions.

Stands alone (standard library only). Wiring it in takes three calls:
    hooks = Webhooks(Path(data_dir) / 'webhooks.json'); hooks.start()
    hooks.emit(kind, actor, target, n)            # beside every audit-log line
    hooks.action(op, payload, domain)             # from the admin action handler
"""
import hashlib, hmac, ipaddress, json, os, queue, re, secrets, socket, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from pathlib import Path

EVENTS = {
    'mail.sent': 'Someone sends a mail',
    'signin.ok': 'Someone signs in',
    'signin.failed': 'A sign-in fails',
    'admin.signin': 'An admin opens the admin console',
    'admin.action': 'An admin changes something (mailbox, domain, policy…)',
}
MAX_PER_DOMAIN = 5
PAUSE_AFTER = 20          # failed deliveries in a row before a webhook is switched off
RETRY_WAITS = (2, 10)     # seconds before the second and third try
DOMAIN = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')


class WebhookError(ValueError):
    """Something the admin can fix; the message is safe to show."""


def event_for(kind):
    """The public event name for an audit-log kind, or '' when that kind is not offered."""
    if kind == 'send': return 'mail.sent'
    if kind == 'signin': return 'signin.ok'
    if kind in ('signin_failed', 'admin_signin_failed'): return 'signin.failed'
    if kind == 'admin_signin': return 'admin.signin'
    if kind.startswith('admin:'): return 'admin.action'
    return ''


def domain_of(email):
    return str(email or '').rpartition('@')[2].strip().lower()


def public_host(host):
    """True when every address of this host is on the public internet (never post into our own network)."""
    try: found = {info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError: return False
    return bool(found) and all(ipaddress.ip_address(a.split('%')[0]).is_global for a in found)


def clean_url(raw, is_public=public_host):
    """The address as it will be stored. Public https only, standard port, no sign-in details inside it."""
    url = str(raw or '').strip()
    parts = urllib.parse.urlsplit(url)
    if len(url) > 500 or parts.scheme != 'https' or not parts.hostname: raise WebhookError('Use a full https:// address.')
    if parts.username or parts.password: raise WebhookError('Remove the user name and password from the address.')
    if parts.port not in (None, 443): raise WebhookError('Use the standard https port.')
    if not is_public(parts.hostname): raise WebhookError('That address is not reachable on the public internet.')
    return urllib.parse.urlunsplit(('https', parts.netloc, parts.path or '/', parts.query, ''))


def sign(secret, stamp, body):
    """v1 signature: HMAC-SHA256 of '<unix time>.<body>' with the webhook's secret."""
    return hmac.new(secret.encode(), f'{stamp}.'.encode() + body, hashlib.sha256).hexdigest()


def verify(secret, header, body, now=None, window=300):
    """What a receiver does: True when the signature fits and the note is at most five minutes old."""
    fields = dict(part.split('=', 1) for part in str(header).split(',') if '=' in part)
    try: stamp = int(fields.get('t', ''))
    except ValueError: return False
    if abs((time.time() if now is None else now) - stamp) > window: return False
    return hmac.compare_digest(sign(secret, stamp, body), fields.get('v1', ''))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def post(url, headers, body, timeout=5):
    """Posts one note. Returns the http status, or 0 when nothing answered. Redirects are not followed."""
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, data=body, headers=headers, method='POST'), timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error: return error.code
    except (OSError, ValueError): return 0


class Webhooks:
    def __init__(self, path, is_public=public_host, post=post, sleep=time.sleep):
        self.path, self.is_public, self.post, self.sleep = Path(path), is_public, post, sleep
        self.lock = threading.Lock()
        self.jobs = queue.Queue(maxsize=1000)
        try: self.all = json.loads(self.path.read_text())
        except (OSError, ValueError): self.all = {}

    # ---- storage ----
    def save(self):
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # holds signing secrets
        with os.fdopen(fd, 'w') as handle: json.dump(self.all, handle)
        os.replace(tmp, self.path)

    @staticmethod
    def public(hook):
        """A webhook as the admin page may see it: the secret never leaves the server again."""
        return {k: hook[k] for k in ('id', 'url', 'events', 'active', 'created', 'last', 'failures')}

    def find(self, domain, hook_id):
        for hook in self.all.get(domain, []):
            if hook['id'] == hook_id: return hook
        raise WebhookError('That webhook no longer exists.')

    # ---- admin actions ----
    def action(self, op, payload, domain):
        """One admin request for one company's domain. Returns what the page should show."""
        domain = str(domain or '').strip().lower()
        if not DOMAIN.fullmatch(domain): raise WebhookError('Choose a domain first.')
        payload = payload if isinstance(payload, dict) else {}
        if op == 'webhook_test': return self.test(domain, str(payload.get('id', '')))
        with self.lock:
            hooks = self.all.setdefault(domain, [])
            if op == 'webhooks_get': return self.listing(domain)
            if op == 'webhook_add':
                if len(hooks) >= MAX_PER_DOMAIN: raise WebhookError(f'A company can have {MAX_PER_DOMAIN} webhooks. Remove one first.')
                events = [e for e in EVENTS if e in (payload.get('events') or [])]
                if not events: raise WebhookError('Pick at least one event.')
                url = clean_url(payload.get('url'), self.is_public)
                if any(h['url'] == url for h in hooks): raise WebhookError('That address is already added.')
                secret = 'whsec_' + secrets.token_urlsafe(32)
                hook = {'id': uuid.uuid4().hex[:12], 'url': url, 'events': events, 'secret': secret, 'active': True,
                        'created': int(time.time()), 'last': None, 'failures': 0}
                hooks.append(hook); self.save()
                return {**self.listing(domain), 'secret': secret, 'id': hook['id']}   # the only time the secret is shown
            hook = self.find(domain, str(payload.get('id', '')))
            if op == 'webhook_remove': hooks.remove(hook)
            elif op == 'webhook_set_active': hook['active'] = bool(payload.get('active')); hook['failures'] = 0
            else: raise WebhookError('Unknown webhook action.')
            self.save()
            return self.listing(domain)

    def listing(self, domain):
        return {'domain': domain, 'webhooks': [self.public(h) for h in self.all.get(domain, [])],
                'events': EVENTS, 'max': MAX_PER_DOMAIN}

    # ---- sending ----
    def emit(self, kind, actor, target='', n=1):
        """Queues a note for every active webhook of the actor's company that asked for this event. Never blocks, never raises."""
        event, domain = event_for(str(kind)), domain_of(actor)
        if not event or not domain: return 0
        note = {'type': event, 'domain': domain, 'actor': str(actor), 'target': str(target or ''), 'count': int(n or 1)}
        if event == 'admin.action': note['action'] = str(kind)[6:]
        queued = 0
        with self.lock: hooks = [dict(h) for h in self.all.get(domain, []) if h['active'] and event in h['events']]
        for hook in hooks:
            try: self.jobs.put_nowait((domain, hook['id'], note)); queued += 1
            except queue.Full: break   # a flood must not grow memory; the audit log still has every event
        return queued

    def deliver(self, hook, note, tries=1 + len(RETRY_WAITS)):
        """Posts one signed note, trying again on no answer or a server error. Returns the last http status (0 = no answer)."""
        body = json.dumps({'id': uuid.uuid4().hex, 'time': int(time.time()), **note}, separators=(',', ':')).encode()
        status = 0
        for attempt in range(tries):
            if attempt: self.sleep(RETRY_WAITS[attempt - 1])
            # checked on every send: the name may point somewhere else than when it was saved
            if not self.is_public(urllib.parse.urlsplit(hook['url']).hostname): status = 0; break
            stamp = int(time.time())
            status = self.post(hook['url'], {'Content-Type': 'application/json', 'User-Agent': 'DejoiyMail-Webhook/1.0',
                'X-Dejoiy-Event': note['type'], 'X-Dejoiy-Signature': f't={stamp},v1={sign(hook["secret"], stamp, body)}'}, body)
            if 200 <= status < 300 or 400 <= status < 500 and status not in (408, 429): break   # a 4xx will not improve by asking again
        return status

    def record(self, domain, hook_id, status):
        with self.lock:
            try: hook = self.find(domain, hook_id)
            except WebhookError: return
            ok = 200 <= status < 300
            hook['last'] = {'at': int(time.time()), 'status': status, 'ok': ok}
            hook['failures'] = 0 if ok else hook['failures'] + 1
            if hook['failures'] >= PAUSE_AFTER: hook['active'] = False
            self.save()

    def test(self, domain, hook_id):
        """Sends a 'ping' now, once, and reports what the other side answered."""
        with self.lock: hook = dict(self.find(domain, hook_id))
        status = self.deliver(hook, {'type': 'ping', 'domain': domain, 'actor': '', 'target': '', 'count': 1}, tries=1)
        self.record(domain, hook_id, status)
        return {**self.listing(domain), 'status': status, 'ok': 200 <= status < 300}

    def work_one(self):
        domain, hook_id, note = self.jobs.get()
        try:
            with self.lock: hook = dict(self.find(domain, hook_id))
            if hook['active']: self.record(domain, hook_id, self.deliver(hook, note))
        except Exception: pass   # one bad webhook must never stop the others
        finally: self.jobs.task_done()

    def start(self):
        # shortcut: one worker, so a slow receiver delays the others by up to ~30 s; add workers when companies use this heavily
        def loop():
            while True: self.work_one()
        threading.Thread(target=loop, name='webhooks', daemon=True).start()
