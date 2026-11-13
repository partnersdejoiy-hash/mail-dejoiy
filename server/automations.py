"""Ready-made automations a company admin switches on in the admin console (Configure > Automations).
They run inside this server, on the new-mail watcher (newmail.py), never in an outside tool.

1. Important mail to Shine ('important_to_shine'): when mail from chosen senders arrives in any mailbox of
   the company, a short message goes to a chosen Shine channel: who sent it and to which mailbox; the
   subject only when the admin switched that on. Never the body. It posts as the admin who saved it,
   so Shine's own rules apply (they must be in that channel).

    autos = Automations(Path(data_dir) / 'automations.json', post=lambda payload: shine_admin_call(...), audit=audit)
    autos.start()                                   # one worker that talks to Shine
    NewMailWatcher(hooks, ..., listeners=[autos])   # autos.domains() / autos.new_mail(...)
"""
import json, os, queue, re, threading, time
from pathlib import Path

KINDS = {
    'important_to_shine': 'Important mail to Shine',
}
MAX_SENDERS = 50
POSTS_PER_HOUR = 30        # per company: a mail storm must not flood a channel
EMAIL = re.compile(r'^[^\s<>@,]+@[^\s<>@,]+\.[^\s<>@,]+$')
DOMAIN = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')


class AutomationError(ValueError):
    """Something the admin can fix; the message is safe to show."""


def clean_senders(raw):
    items = raw if isinstance(raw, list) else re.split(r'[\s,;]+', str(raw or ''))
    out = []
    for item in items:
        s = str(item).strip().lower()
        if not s: continue
        if not (EMAIL.fullmatch(s) or (s.startswith('@') and DOMAIN.fullmatch(s[1:]))):
            raise AutomationError(f'"{s[:80]}" is not an address or @domain.')
        if s not in out: out.append(s)
    if len(out) > MAX_SENDERS: raise AutomationError(f'Choose up to {MAX_SENDERS} senders.')
    return out


def sender_matches(sender, senders):
    sender = str(sender or '').strip().lower()
    return bool(sender) and any(sender == s or (s.startswith('@') and sender.endswith(s)) for s in senders)


class Automations:
    def __init__(self, path, post, audit=None, clock=time.time):
        self.path, self.post, self.audit, self.clock = Path(path), post, audit, clock
        self.lock = threading.Lock()
        self.jobs = queue.Queue(maxsize=500)
        self.posted = {}    # domain -> times of posts in the last hour
        try: self.all = json.loads(self.path.read_text())
        except (OSError, ValueError): self.all = {}

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle: json.dump(self.all, handle)
        os.replace(tmp, self.path)

    # ---- admin actions ----
    def listing(self, domain):
        mine = self.all.get(domain, {})
        imp = mine.get('important_to_shine') or {}
        return {'domain': domain, 'kinds': KINDS, 'important_to_shine': {
            'on': bool(imp.get('on')), 'senders': imp.get('senders', []), 'channel': imp.get('channel', ''),
            'subject': bool(imp.get('subject')), 'by': imp.get('by', ''), 'last': imp.get('last')}}

    def action(self, op, payload, domain, actor):
        domain = str(domain or '').strip().lower()
        if not DOMAIN.fullmatch(domain): raise AutomationError('Choose a domain first.')
        payload = payload if isinstance(payload, dict) else {}
        with self.lock:
            if op == 'automations_get': return self.listing(domain)
            if op != 'automation_save': raise AutomationError('Unknown automation action.')
            kind = payload.get('kind')
            if kind not in KINDS: raise AutomationError('Unknown automation.')
            s = payload.get('settings') if isinstance(payload.get('settings'), dict) else {}
            on = s.get('on') is True
            senders = clean_senders(s.get('senders'))
            channel = str(s.get('channel') or '').strip().lstrip('#')
            if len(channel) > 100 or any(ord(c) < 32 for c in channel): raise AutomationError('Enter a Shine channel name of up to 100 characters.')
            if on and not senders: raise AutomationError('Add at least one sender.')
            if on and not channel: raise AutomationError('Enter the Shine channel to post in.')
            old = self.all.get(domain, {}).get(kind) or {}
            self.all.setdefault(domain, {})[kind] = {'on': on, 'senders': senders, 'channel': channel, 'subject': s.get('subject') is True,
                                                     'by': str(actor or '').lower(), 'saved': int(self.clock()), 'last': old.get('last')}
            self.save()
            return self.listing(domain)

    # ---- the watcher's side ----
    def domains(self):
        """Companies whose mailboxes the new-mail watcher must look at for us."""
        with self.lock: return {d for d, a in self.all.items() if (a.get('important_to_shine') or {}).get('on')}

    def new_mail(self, domain, mailbox, mail):
        """One new inbox mail (id, date, from, subject). Queues a Shine post when it matches. Never blocks, never raises."""
        with self.lock: imp = dict(self.all.get(domain, {}).get('important_to_shine') or {})
        if not imp.get('on') or not sender_matches(mail.get('from'), imp.get('senders', [])): return False
        now = self.clock()
        with self.lock:
            times = [t for t in self.posted.get(domain, []) if t > now - 3600]
            if len(times) >= POSTS_PER_HOUR: self.posted[domain] = times; return False
            self.posted[domain] = times + [now]
        text = f"Important mail for {mailbox} from {mail.get('from')}"
        if imp.get('subject') and mail.get('subject'): text += f"\nSubject: {str(mail['subject'])[:300]}"
        try: self.jobs.put_nowait((domain, mailbox, imp['channel'], imp['by'], text)); return True
        except queue.Full: return False

    def work_one(self):
        domain, mailbox, channel, by, text = self.jobs.get()
        try:
            try: self.post({'op': 'post', 'scope': domain, 'actor': by, 'channel': channel, 'text': text}); last = {'at': int(self.clock()), 'ok': True}
            except Exception as error: last = {'at': int(self.clock()), 'ok': False, 'error': str(error)[:200]}
            with self.lock:
                imp = self.all.get(domain, {}).get('important_to_shine')
                if imp is not None: imp['last'] = last; self.save()
            if self.audit:   # who it was for and where it went; never the subject
                self.audit.add('automation:important_to_shine', mailbox, f"#{channel} {'ok' if last['ok'] else 'failed'}")
        except Exception: pass
        finally: self.jobs.task_done()

    def start(self):
        def loop():
            while True: self.work_one()
        threading.Thread(target=loop, name='automations', daemon=True).start()
