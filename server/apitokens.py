"""API tokens: a company's own scripts and tools call Dejoiy Mail without anyone's password.

A company admin makes a token on Configure > API tokens: a name, what it may do (scopes) and how long
it lives. The token is shown once; this server keeps only its SHA-256 hash, so a copy of the file is
of no use to anyone. Revoking deletes it at once. A token only ever reaches its own company's domain.

Stands alone (standard library only):
    tokens = ApiTokens(Path(data_dir) / 'api-tokens.json')
    tokens.action(op, payload, domain, actor)     # from the admin action handler
    token = tokens.check(raw)                     # None for anything that is not a live token
    tokens.allow(token['id'], scope)              # False when the token is over its rate limit
"""
import hashlib, hmac, json, os, re, secrets, threading, time
from collections import deque
from pathlib import Path

SCOPES = {
    'mail.send': 'Send mail from a mailbox of your company',
    'mail.label': 'Put a label on a mail',
    'mail.read': 'List mail: sender, recipients, subject, date (never the body)',
    'mail.read.body': 'Also read the text of mail (with mail.read)',
    'shine.post': 'Post in a Shine channel of your company',
}
DAYS = (7, 30, 90, 365)
MAX_PER_DOMAIN = 10
PER_MINUTE = 60            # calls per token per minute
SENDS_PER_HOUR = 100       # mails per token per hour
PREFIX = 'dmk_'
TOKEN = re.compile(r'^dmk_([0-9a-f]{12})_([A-Za-z0-9_-]{43})$')
DOMAIN = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')


class TokenError(ValueError):
    """Something the admin can fix; the message is safe to show."""


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiTokens:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.lock = threading.Lock()
        self.calls = {}          # token id -> deque of call times (last minute)
        self.sends = {}          # token id -> deque of send times (last hour)
        self.saved_use = 0.0
        try: self.all = json.loads(self.path.read_text())
        except (OSError, ValueError): self.all = {}

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle: json.dump(self.all, handle)
        os.replace(tmp, self.path)

    @staticmethod
    def public(t):
        """A token as the admin page may see it: never the hash."""
        return {k: t.get(k) for k in ('id', 'name', 'scopes', 'created', 'expires', 'by', 'lastUsed')}

    def listing(self, domain):
        return {'domain': domain, 'tokens': [self.public(t) for t in self.all.get(domain, [])],
                'scopes': SCOPES, 'days': list(DAYS), 'max': MAX_PER_DOMAIN, 'now': int(self.clock())}

    # ---- admin actions ----
    def action(self, op, payload, domain, actor):
        domain = str(domain or '').strip().lower()
        if not DOMAIN.fullmatch(domain): raise TokenError('Choose a domain first.')
        payload = payload if isinstance(payload, dict) else {}
        with self.lock:
            tokens = self.all.setdefault(domain, [])
            if op == 'apitokens_get': return self.listing(domain)
            if op == 'apitoken_add':
                if len(tokens) >= MAX_PER_DOMAIN: raise TokenError(f'A company can have {MAX_PER_DOMAIN} API tokens. Revoke one first.')
                name = str(payload.get('name') or '').strip()
                if not name or len(name) > 60 or any(ord(c) < 32 for c in name): raise TokenError('Give the token a name of up to 60 characters.')
                if any(t['name'].lower() == name.lower() for t in tokens): raise TokenError('A token with that name already exists.')
                wanted = payload.get('scopes') or []
                scopes = [s for s in SCOPES if s in wanted]
                if not scopes: raise TokenError('Pick at least one permission.')
                if 'mail.read.body' in scopes and 'mail.read' not in scopes: raise TokenError('Reading the text of mail needs "mail.read" too.')
                try: days = int(payload.get('days'))
                except (TypeError, ValueError): days = 0
                if days not in DAYS: raise TokenError('Choose how long the token is valid.')
                tid = secrets.token_hex(6)
                raw = PREFIX + tid + '_' + secrets.token_urlsafe(32)
                now = int(self.clock())
                tokens.append({'id': tid, 'name': name, 'scopes': scopes, 'hash': digest(raw), 'created': now,
                               'expires': now + days * 86400, 'by': str(actor or '').lower(), 'lastUsed': None})
                self.save()
                return {**self.listing(domain), 'token': raw, 'id': tid}   # the only time the token is shown
            if op == 'apitoken_revoke':
                tid = str(payload.get('id') or '')
                found = next((t for t in tokens if t['id'] == tid), None)
                if not found: raise TokenError('That token no longer exists.')
                tokens.remove(found); self.save()
                self.calls.pop(tid, None); self.sends.pop(tid, None)
                return {**self.listing(domain), 'revoked': found['name']}
            raise TokenError('Unknown API token action.')

    # ---- calls ----
    def check(self, raw):
        """The live token for this bearer value (with its domain), or None. Same answer for every kind of wrong."""
        match = TOKEN.fullmatch(str(raw or '').strip())
        if not match: return None
        tid, want, now = match.group(1), digest(match.group(0)), self.clock()
        with self.lock:
            for domain, tokens in self.all.items():
                for t in tokens:
                    if t['id'] != tid: continue
                    if not hmac.compare_digest(t['hash'], want) or t['expires'] <= now: return None
                    t['lastUsed'] = int(now)
                    if now - self.saved_use > 300:   # 'last used' reaches the disk at most every 5 minutes
                        self.saved_use = now
                        try: self.save()
                        except OSError: pass
                    return {**self.public(t), 'domain': domain}
        return None

    def allow(self, tid, scope):
        """Counts one call; False when the token is over its limit (the call is then not counted)."""
        now = self.clock()
        with self.lock:
            calls = self.calls.setdefault(tid, deque())
            while calls and calls[0] <= now - 60: calls.popleft()
            if len(calls) >= PER_MINUTE: return False
            if scope == 'mail.send':
                sends = self.sends.setdefault(tid, deque())
                while sends and sends[0] <= now - 3600: sends.popleft()
                if len(sends) >= SENDS_PER_HOUR: return False
                sends.append(now)
            calls.append(now)
            return True
