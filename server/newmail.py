"""Tells a company's webhooks when a mail arrives ('mail.received').

Incoming mail goes straight into the mail store and never passes this server, so this looks:
once a minute, and only for companies that have an active webhook asking for it, it reads the
newest inbox headers of each of their mailboxes and reports the ones that were not there before.
The note says which mailbox, who it is from and the message id. Never the subject or the body.

    watcher = NewMailWatcher(hooks, mailboxes=lambda domain: [emails], inbox=lambda email: [{'id','date','from'}])
    watcher.start()
"""
import threading, time

EVENT = 'mail.received'
MAX_BOXES = 300   # per company, per round


class NewMailWatcher:
    def __init__(self, hooks, mailboxes, inbox, every=60):
        self.hooks, self.mailboxes, self.inbox, self.every = hooks, mailboxes, inbox, every
        self.seen = {}   # mailbox -> date (ms) of the newest mail already reported

    def check(self):
        """One round. Returns how many notes were queued."""
        queued, seen = 0, {}
        for domain in sorted(self.hooks.wanting(EVENT)):
            try: boxes = list(self.mailboxes(domain))[:MAX_BOXES]
            except Exception: continue          # the mail server is busy or down: try again next round
            for email in boxes:
                try: mails = self.inbox(email)
                except Exception:
                    if email in self.seen: seen[email] = self.seen[email]
                    continue
                newest = max((m['date'] for m in mails), default=0)
                last = self.seen.get(email)
                # a mailbox seen for the first time only sets the line: mail that was already there is not news
                if last is not None:
                    for m in sorted((m for m in mails if m['date'] > last), key=lambda m: m['date']):
                        queued += self.hooks.send(EVENT, domain, {'actor': m.get('from', ''), 'target': email, 'count': 1, 'message': str(m['id'])})
                seen[email] = max(newest, last or 0)
        # shortcut: kept in memory, so mail that arrives while the server restarts is not reported; store it when someone depends on every single one
        self.seen = seen   # mailboxes no longer watched are forgotten, so old mail is not reported if they are watched again
        return queued

    def start(self):
        def loop():
            while True:
                time.sleep(self.every)
                try: self.check()
                except Exception: pass
        threading.Thread(target=loop, name='newmail', daemon=True).start()
