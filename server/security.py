"""Spam and phishing marks on incoming mail, and the admin's list of everything that was marked.

risk() reads what the mail system already knows about a message (our own server's SPF/DKIM/DMARC stamp and
spam score) plus what the message itself shows (display name, links, attachments, wording) and returns a level:
  'phishing'   tries to pass as someone it is not, or to get a password, payment or OTP out of the reader
  'suspicious' looks like spam or junk
  None         nothing worth a mark
with plain-language reasons. The same function marks mail in the reader's list and fills the admin's list,
which a watcher keeps current for every mailbox as mail arrives.
"""
import json, re, sqlite3, threading, time
from html.parser import HTMLParser
from urllib.parse import urlsplit

FREE_MAIL = {'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.in', 'ymail.com', 'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
             'icloud.com', 'me.com', 'aol.com', 'proton.me', 'protonmail.com', 'rediffmail.com', 'zohomail.in', 'gmx.com', 'yandex.com', 'mail.com'}
# Names people trust; a sender using one in its display name from somewhere else is the classic phishing trick.
BRANDS = {'paypal': 'paypal.com', 'amazon': 'amazon', 'google': 'google.com', 'gmail': 'google.com', 'microsoft': 'microsoft.com',
          'office 365': 'microsoft.com', 'outlook': 'microsoft.com', 'apple': 'apple.com', 'icloud': 'apple.com', 'netflix': 'netflix.com',
          'facebook': 'facebook.com', 'instagram': 'instagram.com', 'whatsapp': 'whatsapp.com', 'linkedin': 'linkedin.com',
          'sbi': 'sbi.co.in', 'state bank': 'sbi.co.in', 'hdfc': 'hdfc', 'icici': 'icici', 'axis bank': 'axisbank', 'kotak': 'kotak',
          'paytm': 'paytm', 'phonepe': 'phonepe', 'razorpay': 'razorpay', 'income tax': 'gov.in', 'uidai': 'gov.in', 'aadhaar': 'gov.in',
          'dejoiy': 'dejoiy.com', 'zoho': 'zoho', 'docusign': 'docusign', 'dhl': 'dhl', 'fedex': 'fedex'}
LURES = re.compile(r'verify (your|the) account|confirm your (password|identity|account)|password (will )?expir|account (has been |will be )?(suspended|locked|closed|blocked)'
                   r'|unusual sign[- ]?in|update (your )?(kyc|payment|billing)|kyc (update|pending|expired)|share (the )?otp|enter (your )?otp'
                   r'|gift ?card|lottery|you have won|claim your (prize|reward|refund)|wire transfer|bitcoin|crypto wallet|inheritance'
                   r'|urgent(ly)? (action|response|payment)|act now|within 24 hours|final (notice|warning)|click (here|below) to (login|log in|sign in|verify)'
                   r'|mailbox (is )?full|storage (is )?full|invoice attached.*(enable|macro)', re.I)
DANGEROUS = re.compile(r'\.(exe|scr|com|pif|bat|cmd|js|jse|vbs|vbe|wsf|hta|msi|jar|ps1|lnk|iso|img|reg|cpl)$', re.I)
DOUBLE = re.compile(r'\.(pdf|docx?|xlsx?|jpe?g|png|txt)\.(exe|scr|js|vbs|bat|cmd|html?|hta|lnk|iso)$', re.I)
SHORTENERS = {'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'is.gd', 'cutt.ly', 'rb.gy', 'ow.ly', 'shorturl.at', 'tiny.cc', 'rebrand.ly'}
IP_HOST = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$|^\[?[0-9a-f:]+\]?$', re.I)
DOMAINISH = re.compile(r'^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/\S*)?$', re.I)
CONFUSABLE = str.maketrans({'0': 'o', '1': 'l', '3': 'e', '5': 's', '@': 'a', '$': 's', 'l': 'l', 'i': 'l', 'I': 'l'})


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.href = None; self.text = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.href = dict(attrs).get('href') or ''; self.text = []
    def handle_data(self, data):
        if self.href is not None: self.text.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None: self.links.append((self.href.strip(), ''.join(self.text).strip())); self.href = None


def links(html_text):
    p = _Links()
    try: p.feed(html_text or ''); p.close()
    except Exception: pass
    return p.links


def site(host):
    """example.co.in for mail.example.co.in: what a person reads as 'the company'."""
    parts = (host or '').lower().strip('.').split('.')
    keep = 3 if len(parts) >= 3 and parts[-2] in ('co', 'com', 'org', 'net', 'gov', 'ac', 'edu') and len(parts[-1]) == 2 else 2
    return '.'.join(parts[-keep:])


def _close(a, b):
    """True when two names differ by one or two typed characters (dej0iy / dejoly vs dejoiy)."""
    if a == b or abs(len(a) - len(b)) > 2: return False
    if a.translate(CONFUSABLE) == b.translate(CONFUSABLE): return True
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1): cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= (1 if len(b) <= 6 else 2)


def auth_results(results, authserv):
    """{'spf':…, 'dkim':…, 'dmarc':…} from the Authentication-Results our own server stamped (others can be forged)."""
    out = {}
    for value in results or []:
        text = re.sub(r'\s+', ' ', str(value or '')).strip().lower()
        if text.split(';', 1)[0].strip().split(' ')[0] != str(authserv).lower(): continue
        for k in ('spf', 'dkim', 'dmarc'):
            m = re.search(r'(?:^|[;\s])' + k + r'=([a-z]+)', text)
            if m and k not in out: out[k] = m.group(1)
    return out


def risk(*, sender, name='', reply_to='', subject='', html_body='', text_body='', attachments=(), auth=None,
         spam_flag='', spam_score=None, verified=False, own_domains=(), recipient=''):
    """Scores one message. Returns {'level', 'score', 'reasons'} (level None when it looks fine)."""
    sender = (sender or '').lower(); domain = sender.rsplit('@', 1)[-1] if '@' in sender else ''
    company = site(domain); auth = auth or {}
    reasons, phish, junk = [], 0, 0
    def hit(kind, points, why):
        nonlocal phish, junk
        if kind == 'p': phish += points
        else: junk += points
        if why not in reasons: reasons.append(why)

    # what our own mail server found
    if str(spam_flag).strip().upper().startswith('YES'): hit('j', 4, 'The mail server’s spam filter marked it as spam.')
    try: score = float(spam_score) if spam_score not in (None, '') else None
    except ValueError: score = None
    if score is not None and score >= 5: hit('j', 3, f'High spam score ({score:g}).')
    elif score is not None and score >= 3: hit('j', 1, f'Raised spam score ({score:g}).')
    if auth.get('dmarc') == 'fail': hit('p', 4, f'It says it is from {domain}, but {domain}’s own checks (DMARC) failed.')
    if auth.get('spf') in ('fail', 'softfail'): hit('p' if auth.get('dmarc') != 'pass' else 'j', 2, f'It was not sent from a server {domain} allows (SPF {auth["spf"]}).')
    if auth.get('dkim') == 'fail': hit('j', 1, 'Its signature (DKIM) does not match.')

    # pretending to be someone else
    own = {site(d) for d in own_domains if d} | ({site(recipient.rsplit('@', 1)[-1])} if '@' in recipient else set())
    if domain in own or company in own:
        if not verified and auth.get('dmarc') != 'pass' and auth: hit('p', 4, f'It claims to come from your own company ({domain}) but was not sent by your mail server.')
    else:
        for o in own:
            if _close(company.split('.')[0], o.split('.')[0]): hit('p', 5, f'{domain} looks like your own {o}, but is a different domain.'); break
    shown = (name or '').lower()
    in_name = re.search(r'[\w.+-]+@([\w-]+\.[\w.-]+)', shown)
    if in_name and site(in_name.group(1)) != company: hit('p', 3, f'The name shows the address {in_name.group(0)}, but it came from {sender}.')
    for brand, home in BRANDS.items():
        if re.search(r'\b' + re.escape(brand) + r'\b', shown) and home.split('.')[0] not in domain:
            hit('p', 3 if domain in FREE_MAIL or not verified else 2, f'The name says “{brand.title()}”, but it came from {domain}.'); break
    if reply_to and '@' in reply_to:
        rdomain = reply_to.lower().rsplit('@', 1)[-1]
        if site(rdomain) != company and (rdomain in FREE_MAIL or not verified):
            hit('p', 2, f'Replies would go to a different address ({reply_to}).')

    # what it asks the reader to do
    words = (subject or '') + ' ' + (text_body or '')[:20000]
    lures = {m.group(0).lower() for m in LURES.finditer(words)}
    if lures: hit('p', min(3, len(lures) + 1), 'It asks for something scammers ask for (' + ', '.join(sorted(lures))[:80] + ').')
    for href, label in links(html_body)[:200]:
        u = urlsplit(href if '//' in href else '')
        host = (u.hostname or '').lower()
        if not host: continue
        if u.username or '@' in (u.netloc or ''): hit('p', 3, 'A link hides its real address with an “@” trick.')
        if IP_HOST.match(host): hit('p', 2, f'A link goes to a bare server address ({host}).')
        if host in SHORTENERS: hit('j', 1, 'It uses link shorteners that hide where links go.')
        if DOMAINISH.match(label or ''):
            shown_host = (urlsplit(label if '//' in label else '//' + label).hostname or '').lower()
            # newsletters from a verified sender often show their own address over a click-tracking link: only a nudge there
            if shown_host and site(shown_host) != site(host):
                if verified: hit('j', 1, f'A link shows {shown_host} but goes through {host}.')
                else: hit('p', 5, f'A link shows {shown_host} but really goes to {host}.')
    for f in attachments or ():
        f = str(f or '')
        if DOUBLE.search(f): hit('p', 5, f'The attachment “{f}” hides a program behind a document name.')
        elif DANGEROUS.search(f): hit('p', 3, f'The attachment “{f}” is a program or script.')
        elif re.search(r'\.html?$', f, re.I): hit('p', 2, f'The attachment “{f}” is a web page (often a fake sign-in form).')

    if verified and phish: phish -= 2   # the domain really sent it: less likely to be an impostor
    total = phish + junk
    level = 'phishing' if phish >= 5 else 'suspicious' if total >= 3 else None
    return {'level': level, 'score': total, 'reasons': reasons if level else []}


class SecurityLog:
    """Every message that got a mark, for the admin console (kept 90 days)."""
    KEEP = 90 * 86400
    def __init__(self, path=None):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path or ':memory:', check_same_thread=False)
        self.db.execute('''CREATE TABLE IF NOT EXISTS flagged (mailbox TEXT NOT NULL, msg_id TEXT NOT NULL, domain TEXT NOT NULL, at REAL NOT NULL,
            sender TEXT, name TEXT, subject TEXT, level TEXT NOT NULL, score INTEGER, reasons TEXT, PRIMARY KEY (mailbox, msg_id))''')
        self.db.execute('CREATE INDEX IF NOT EXISTS flagged_at ON flagged(domain, at)'); self.db.commit()

    def record(self, mailbox, msg_id, sender, name, subject, verdict, at=None):
        if not verdict.get('level'): return False
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO flagged VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (mailbox.lower(), str(msg_id), mailbox.lower().rsplit('@', 1)[-1], at or time.time(), sender, name, (subject or '')[:300],
                             verdict['level'], verdict['score'], json.dumps(verdict['reasons'])))
            self.db.execute('DELETE FROM flagged WHERE at<?', (time.time() - self.KEEP,)); self.db.commit()
        return True

    def list(self, domains=None, level=None, days=30, limit=500):
        """domains None = every company (Dejoiy super admins)."""
        sql, args = 'SELECT mailbox, msg_id, at, sender, name, subject, level, score, reasons FROM flagged WHERE at>?', [time.time() - days * 86400]
        if domains is not None:
            if not domains: return {'items': [], 'counts': {}}
            sql += ' AND domain IN (%s)' % ','.join('?' * len(domains)); args += list(domains)
        with self.lock:
            counts = dict(self.db.execute(sql.replace('SELECT mailbox, msg_id, at, sender, name, subject, level, score, reasons', 'SELECT level, COUNT(*)') + ' GROUP BY level', args).fetchall())
            if level: sql += ' AND level=?'; args.append(level)
            rows = self.db.execute(sql + ' ORDER BY at DESC LIMIT ?', args + [limit]).fetchall()
        return {'counts': counts, 'items': [{'mailbox': r[0], 'id': r[1], 'at': int(r[2]), 'from': r[3], 'name': r[4], 'subject': r[5],
                                              'level': r[6], 'score': r[7], 'reasons': json.loads(r[8] or '[]')} for r in rows]}

    def counts(self, since):
        with self.lock: return dict(self.db.execute('SELECT level, COUNT(*) FROM flagged WHERE at>? GROUP BY level', (since,)).fetchall())


class SecurityScanner:
    """A listener on the new-mail watcher: every new message in every mailbox is scored and, when marked, logged."""
    def __init__(self, log, all_domains, verdict_for):
        self.log, self.all_domains, self.verdict_for = log, all_domains, verdict_for
    def domains(self):
        try: return set(self.all_domains())
        except Exception: return set()
    def new_mail(self, domain, mailbox, mail):
        found = self.verdict_for(mailbox, mail['id'])
        if found: self.log.record(mailbox, mail['id'], found['from'], found['name'], found['subject'], found['risk'], at=mail.get('date', 0) / 1000 or None)
