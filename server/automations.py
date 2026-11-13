"""Ready-made automations a company admin switches on in the admin console (Configure > Automations).
They run inside this server (the new-mail watcher in newmail.py and an hourly round here), never in an outside tool.

1. Important mail to Shine ('important_to_shine'): when mail from chosen senders arrives in any mailbox of
   the company, a short message goes to a chosen Shine channel: who sent it and to which mailbox; the
   subject only when the admin switched that on. Never the body. It posts as the admin who saved it,
   so Shine's own rules apply (they must be in that channel).
2. Follow-up reminder ('followup'): when someone's sent mail has had no reply for N days, a reminder lands
   in that person's own inbox. Only mail sent after the reminder was switched on; each mail at most once.

    autos = Automations(Path(data_dir) / 'automations.json', post=lambda payload: shine_admin_call(...), audit=audit, mail=MailSide(...))
    autos.start()                                   # one worker that talks to Shine, one hourly follow-up round
    NewMailWatcher(hooks, ..., listeners=[autos])   # autos.domains() / autos.new_mail(...)
"""
import json, os, queue, re, threading, time
from pathlib import Path

KINDS = {
    'important_to_shine': 'Important mail to Shine',
    'followup': 'Follow-up reminder',
}
MAX_SENDERS = 50
POSTS_PER_HOUR = 30        # per company: a mail storm must not flood a channel
FOLLOWUP_DAYS = (1, 2, 3, 5, 7, 14)
FOLLOWUP_GRACE = 3         # days after the due day a mail is still looked at (server down, busy ...)
REMINDERS_PER_ROUND = 10   # per mailbox
MAX_BOXES = 300            # per company, per round
DAY = 86400
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


def reminder_text(mail, days, when):
    """The reminder's subject and text: the person's own mail, so its subject and recipients may be named."""
    subject = str(mail.get('subject') or '(no subject)')[:200]
    to = ', '.join(mail.get('to', [])[:5]) + (' and others' if len(mail.get('to', [])) > 5 else '')
    return (f'Reminder: no reply yet to "{subject}"',
            f'You sent "{subject}" to {to} on {when}, and no reply has come in {days} day{"s" if days > 1 else ""}.\n\n'
            'Maybe follow up? This reminder comes from the Follow-up reminder your company switched on in Dejoiy Mail.')


class Automations:
    def __init__(self, path, post, audit=None, clock=time.time, mail=None):
        self.path, self.post, self.audit, self.clock, self.mail = Path(path), post, audit, clock, mail
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

    def setting(self, domain, kind):
        return self.all.get(domain, {}).get(kind) or {}

    # ---- admin actions ----
    def listing(self, domain):
        imp, fu = self.setting(domain, 'important_to_shine'), self.setting(domain, 'followup')
        return {'domain': domain, 'kinds': KINDS,
                'important_to_shine': {'on': bool(imp.get('on')), 'senders': imp.get('senders', []), 'channel': imp.get('channel', ''),
                                       'subject': bool(imp.get('subject')), 'by': imp.get('by', ''), 'last': imp.get('last')},
                'followup': {'on': bool(fu.get('on')), 'days': fu.get('days', 3), 'choices': list(FOLLOWUP_DAYS), 'since': fu.get('since'),
                             'by': fu.get('by', ''), 'last': fu.get('last'), 'available': self.mail is not None}}

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
            on, old, now = s.get('on') is True, self.setting(domain, kind), int(self.clock())
            if kind == 'important_to_shine':
                senders = clean_senders(s.get('senders'))
                channel = str(s.get('channel') or '').strip().lstrip('#')
                if len(channel) > 100 or any(ord(c) < 32 for c in channel): raise AutomationError('Enter a Shine channel name of up to 100 characters.')
                if on and not senders: raise AutomationError('Add at least one sender.')
                if on and not channel: raise AutomationError('Enter the Shine channel to post in.')
                new = {'on': on, 'senders': senders, 'channel': channel, 'subject': s.get('subject') is True}
            else:
                if on and self.mail is None: raise AutomationError('Follow-up reminders are not available on this server.')
                try: days = int(s.get('days'))
                except (TypeError, ValueError): days = 0
                if days not in FOLLOWUP_DAYS: raise AutomationError('Choose after how many days.')
                # only mail sent from the moment it is switched on: switching on never reminds about old mail
                new = {'on': on, 'days': days, 'since': (old.get('since') if old.get('on') else now) if on else None, 'done': old.get('done', {}) if on else {}}
            self.all.setdefault(domain, {})[kind] = {**new, 'by': str(actor or '').lower(), 'saved': now, 'last': old.get('last')}
            self.save()
            return self.listing(domain)

    # ---- 1. important mail to Shine (the watcher's side) ----
    def domains(self):
        """Companies whose mailboxes the new-mail watcher must look at for us."""
        with self.lock: return {d for d, a in self.all.items() if (a.get('important_to_shine') or {}).get('on')}

    def new_mail(self, domain, mailbox, mail):
        """One new inbox mail (id, date, from, subject). Queues a Shine post when it matches. Never blocks, never raises."""
        with self.lock: imp = dict(self.setting(domain, 'important_to_shine'))
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
            try: self.post({'op': 'post', 'scope': domain, 'actor': by, 'channel': channel, 'text': text, 'via': 'automation'}); last = {'at': int(self.clock()), 'ok': True}
            except Exception as error: last = {'at': int(self.clock()), 'ok': False, 'error': str(error)[:200]}
            with self.lock:
                imp = self.all.get(domain, {}).get('important_to_shine')
                if imp is not None: imp['last'] = last; self.save()
            if self.audit:   # who it was for and where it went; never the subject
                self.audit.add('automation:important_to_shine', mailbox, f"#{channel} {'ok' if last['ok'] else 'failed'}")
        except Exception: pass
        finally: self.jobs.task_done()

    # ---- 2. follow-up reminder (hourly) ----
    def followups(self):
        """One round over every company that switched reminders on. Returns how many reminders went out."""
        if self.mail is None: return 0
        with self.lock: wanted = {d: dict(a['followup']) for d, a in self.all.items() if (a.get('followup') or {}).get('on')}
        total = 0
        for domain, fu in sorted(wanted.items()):
            now = self.clock(); due = now - fu['days'] * DAY
            oldest = max(fu['since'], due - FOLLOWUP_GRACE * DAY)
            done = {box: dict(ids) for box, ids in (fu.get('done') or {}).items()}
            sent = errors = 0
            try: boxes = list(self.mail.mailboxes(domain))[:MAX_BOXES]
            except Exception: continue   # the mail server is busy: next hour
            for box in boxes:
                mine = done.setdefault(box, {}); count = 0
                try: mails = self.mail.sent(box, int(oldest * 1000))
                except Exception: errors += 1; continue
                for m in sorted(mails, key=lambda m: m['date']):
                    if count >= REMINDERS_PER_ROUND: break
                    at = m['date'] / 1000
                    if str(m['id']) in mine or not oldest <= at <= due: continue
                    others = [a for a in m.get('to', []) if a.lower() != box]
                    try:
                        if not others or self.mail.replied(box, m):
                            mine[str(m['id'])] = int(at); continue   # a reply came (or it went only to themselves): never remind
                        subject, text = reminder_text(m, fu['days'], time.strftime('%d %b %Y, %H:%M', time.localtime(at)))
                        self.mail.remind(box, subject, text)
                    except Exception: errors += 1; continue
                    mine[str(m['id'])] = int(at); count += 1; sent += 1
                    if self.audit: self.audit.add('automation:followup', box, 'reminded about mail ' + str(m['id']))
            keep = now - (fu['days'] + FOLLOWUP_GRACE + 1) * DAY   # older mail is never looked at again
            with self.lock:
                current = self.all.get(domain, {}).get('followup')
                if current and current.get('on') and current.get('since') == fu['since']:
                    current['done'] = {box: {i: t for i, t in ids.items() if t >= keep} for box, ids in done.items() if any(t >= keep for t in ids.values())}
                    current['last'] = {'at': int(now), 'ok': errors == 0, 'reminders': sent, **({'error': f'{errors} mailbox(es) could not be checked'} if errors else {})}
                    self.save()
            total += sent
        return total

    def start(self, every=3600, first=300):
        def posts():
            while True: self.work_one()
        def rounds():
            time.sleep(first)
            while True:
                try: self.followups()
                except Exception: pass
                time.sleep(every)
        threading.Thread(target=posts, name='automations', daemon=True).start()
        threading.Thread(target=rounds, name='followups', daemon=True).start()
