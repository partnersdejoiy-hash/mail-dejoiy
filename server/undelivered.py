"""Undelivered mail: every message that was stopped, bounced, rejected or is still waiting, read
from the real Postfix and amavis logs, for the admin console's Monitor > Undelivered mail page.

Rule this page exists for: a message somebody sent that was not delivered must never vanish
silently. Each row says what happened, why, and whether the sender (or recipient) was told.

    sudo python3 undelivered.py --index       # rebuild the index from /var/log (run by a root timer)
    python3 undelivered.py --show [domain]    # print what the page would show

The web app runs as an unprivileged user and cannot read the system logs, so a root timer
writes a small SQLite index (/var/lib/dmail/undelivered.db, root:dmail 0640) that the app reads.
Only envelope data is stored: time, queue id, sender, recipient, status and reason. Never content.
"""
import gzip
import os
import re
import sqlite3
import sys
import time
from datetime import datetime

DB_PATH = os.environ.get('DMAIL_UNDELIVERED_DB', '/var/lib/dmail/undelivered.db')
MAIL_LOGS = ('/var/log/mail.log.2.gz', '/var/log/mail.log.1', '/var/log/mail.log')  # postfix, ISO timestamps
AMAVIS_LOGS = ('/var/log/zimbra.log.4.gz', '/var/log/zimbra.log.3.gz', '/var/log/zimbra.log.2.gz',
               '/var/log/zimbra.log.1.gz', '/var/log/zimbra.log')  # amavis verdicts, syslog timestamps
KEEP_DAYS = 30
SHOW_DAYS = 14

# Ports of the content filter (see amavisd.conf): which way the message was going.
OUTBOUND_PORTS = ('10026', '10032')
INBOUND_PORTS = ('10024',)

ISO = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\S*\s+\S+\s+(\S+?)(?:\[\d+\])?:\s+(.*)$')
SYSLOG = re.compile(r'^([A-Z][a-z]{2})\s+(\d{1,2}) (\d\d:\d\d:\d\d)\s+\S+\s+(\S+?)(?:\[\d+\])?:\s+(.*)$')
QID = r'([0-9A-F]{6,}|[0-9B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]{10,})'
R_FROM = re.compile(QID + r': from=<([^>]*)>')
R_DELIVERY = re.compile(QID + r': to=<([^>]*)>,(?: orig_to=<[^>]*>,)? relay=([^,]+), .*?dsn=([\d.]+), status=(\w+) \((.*)\)\s*$')
R_NOTICE = re.compile(QID + r': sender (non-delivery|delay) notification: ')
R_CLIENT = re.compile(QID + r': client=(\S+)')
R_REJECT = re.compile(r'NOQUEUE: reject: (\S+) from (\S+): (\d{3} [\d.]+ .*?); (?:from=<([^>]*)>)?(?: to=<([^>]*)>)?')
R_AMAVIS = re.compile(r'\((\d+-\d+)\) Blocked ([A-Z-]+)(?: \(([^)]*)\))? \{([^}]*)\}.*?<([^>]*)> -> (.*?), (?:quarantine|Queue-ID|Message-ID)')
R_AMAVIS_ID = re.compile(r'(?:discarded, id=|Ok, id=)(\d+-\d+)')
OUR_HOSTS = ('173.249.23.93', '127.0.0.1')

PLAIN = {  # plain-language reason shown to admins (and the same idea as the bounce text senders get)
    'INFECTED': 'Attachment mein virus mila',
    'BANNED': 'Attachment ka file type allowed nahi hai',
    'SPAM': 'Mail spam jaisi lagi',
    'SPAMMY': 'Mail spam jaisi lagi',
    'BAD-HEADER': 'Mail ke headers galat the',
    'OVERSIZED': 'Mail bahut badi thi',
    'UNCHECKED': 'Mail ki jaanch nahi ho saki',
}


def _open(path):
    try:
        return gzip.open(path, 'rt', errors='replace') if path.endswith('.gz') else open(path, errors='replace')
    except OSError:
        return None


def _syslog_ts(mon, day, hms, now):
    """Syslog lines carry no year: use this year, or last year for a month that is still ahead."""
    try:
        t = datetime.strptime(f'{now.year} {mon} {int(day)} {hms}', '%Y %b %d %H:%M:%S')
    except ValueError:
        return None
    if t > now and (t - now).days > 1: t = t.replace(year=now.year - 1)
    return t.timestamp()


def domain_of(address):
    address = (address or '').strip().lower()
    return address.rsplit('@', 1)[1] if '@' in address else ''


def reason_text(raw, verdict=None):
    """'552 5.3.4 Message size exceeds fixed limit' -> a short plain sentence plus the server's words."""
    if verdict:
        kind, name = verdict
        return PLAIN.get(kind, kind.title()) + (f' ({name})' if name else '')
    r = raw or ''
    low = r.lower()
    if 'size exceeds' in low or ' 5.3.4' in r or 'message file too big' in low: plain = 'Mail size limit se badi thi'
    elif 'host or domain name not found' in low or 'name service error' in low or ' 5.4.4' in r: plain = 'Ye domain maujood nahi hai'
    elif 'user does not exist' in low or 'user unknown' in low or 'no such user' in low or ' 5.1.1' in r: plain = 'Ye mailbox maujood nahi hai'
    elif 'policy' in low or ' 5.7.' in r: plain = 'Paane wale server ne policy ki wajah se mana kiya'
    elif 'connection refused' in low or 'timed out' in low or 'connect to' in low: plain = 'Paane wala server abhi jawab nahi de raha'
    elif 'mailbox full' in low or 'quota' in low or ' 5.2.2' in r or ' 4.2.2' in r: plain = 'Paane wale ka mailbox bhara hua hai'
    elif re.fullmatch(r'[a-z0-9.-]+', low): plain = 'Is server pe ye mailbox maujood nahi hai'
    else: plain = 'Mail server ne mail nahi li'
    return plain + (': ' + r[:300] if r else '')


def parse(mail_lines, amavis_lines=(), now=None):
    """Turn log lines into undelivered-mail rows. Lines are (path-independent) raw strings."""
    now_dt = datetime.fromtimestamp(now) if now else datetime.now()
    senders, clients, notices, verdicts = {}, {}, {}, {}
    finals = {}     # (qid, rcpt) -> latest delivery outcome dict
    rejects = []
    ses_bounces = []

    for line in amavis_lines:
        m = SYSLOG.match(line)
        if not m or not m.group(4).startswith('amavis'): continue
        b = R_AMAVIS.search(m.group(5))
        if b: verdicts[b.group(1)] = (b.group(2), (b.group(3) or '').strip())

    for line in mail_lines:
        m = ISO.match(line)
        if not m: continue
        try: ts = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').timestamp()
        except ValueError: continue
        prog, msg = m.group(2), m.group(3)
        if not prog.startswith('postfix'): continue
        f = R_FROM.search(msg)
        if f: senders.setdefault(f.group(1), f.group(2)); continue
        c = R_CLIENT.search(msg)
        if c: clients.setdefault(c.group(1), c.group(2)); continue
        n = R_NOTICE.search(msg)
        if n: notices.setdefault(n.group(1), set()).add(n.group(2)); continue
        d = R_DELIVERY.search(msg)
        if d:
            qid, rcpt, relay, dsn, status, text = d.groups()
            finals[(qid, rcpt.lower())] = {'ts': ts, 'qid': qid, 'rcpt': rcpt.lower(), 'relay': relay, 'dsn': dsn, 'status': status, 'text': text}
            continue
        r = R_REJECT.search(msg)
        if r and any(h in r.group(2) for h in OUR_HOSTS):
            rejects.append({'ts': ts, 'stage': r.group(1), 'text': r.group(3), 'from': (r.group(4) or '').lower(), 'to': (r.group(5) or '').lower()})

    rows = []
    for (qid, rcpt), o in finals.items():
        sender = (senders.get(qid) or '').lower()
        relay, status, text = o['relay'], o['status'], o['text']
        port = relay.rsplit(':', 1)[-1] if relay.startswith('127.0.0.1') else ''
        row = None
        if port and status == 'sent':
            # content-filter hop: only interesting when amavis stopped the message
            aid = R_AMAVIS_ID.search(text)
            verdict = verdicts.get(aid.group(1)) if aid else None
            direction = 'outbound' if port in OUTBOUND_PORTS else 'inbound'
            if ', discarded' in text:
                kind = text.split(' - ', 1)[1].split(':', 1)[0].strip() if ' - ' in text else ''
                name = text.split(':', 1)[1].strip().rstrip(')') if ' - ' in text and ':' in text.split(' - ', 1)[1] else ''
                v = verdict or ((kind, name) if kind else None)
                told = 'no' if direction == 'outbound' else 'recipient'
                row = {'outcome': 'stopped', 'action': 'discarded', 'direction': direction, 'reason': reason_text(text, v), 'notified': told}
            elif text.rstrip().endswith('BOUNCE'):
                row = {'outcome': 'stopped', 'action': 'bounced', 'direction': direction, 'reason': reason_text(text, verdict),
                       'notified': 'sender'}
        elif status in ('bounced', 'expired'):
            told = 'sender' if 'non-delivery' in notices.get(qid, set()) else 'no'
            if not sender: told = 'no'  # a bounce of a bounce has nobody to tell
            if sender == rcpt and relay == 'none': told = 'no'  # the notice goes to the same missing mailbox
            row = {'outcome': 'bounced' if status == 'bounced' else 'expired', 'action': 'returned', 'direction': 'outbound' if domain_of(sender) else 'system',
                   'reason': reason_text(text), 'notified': told}
        elif status == 'deferred':
            told = 'sender (delay notice)' if 'delay' in notices.get(qid, set()) else 'not yet'
            row = {'outcome': 'waiting', 'action': 'deferred', 'direction': 'outbound', 'reason': reason_text(text), 'notified': told}
        if row:
            row.update({'ts': o['ts'], 'qid': qid, 'from': sender or '(system)', 'to': rcpt})
            rows.append(row)
        # Amazon SES reports a remote bounce back as a new message from <> to our sender.
        if sender == '' and 'amazonses.com' in (clients.get(qid) or '') and status == 'sent':
            ses_bounces.append({'ts': o['ts'], 'qid': qid, 'from': rcpt, 'to': '(see bounce in inbox)', 'outcome': 'bounced', 'action': 'returned',
                                'direction': 'outbound', 'reason': 'Amazon SES ne paane wale ke server ka bounce lautaya (poori wajah bhejne wale ke inbox mein)',
                                'notified': 'sender'})
    for r in rejects:
        rows.append({'ts': r['ts'], 'qid': '', 'from': r['from'] or '(unknown)', 'to': r['to'] or '(all recipients)', 'outcome': 'rejected', 'action': 'refused',
                     'direction': 'outbound', 'reason': reason_text(r['text']), 'notified': 'sender (at send time)'})
    rows.extend(ses_bounces)
    rows.sort(key=lambda x: -x['ts'])
    return rows


def read_logs(mail_logs=MAIL_LOGS, amavis_logs=AMAVIS_LOGS):
    def lines(paths):
        for p in paths:
            fh = _open(p)
            if fh is None: continue
            with fh:
                yield from fh
    return lines(mail_logs), lines(amavis_logs)


SCHEMA = ('CREATE TABLE rows (ts REAL, qid TEXT, sender TEXT, sender_domain TEXT, rcpt TEXT, rcpt_domain TEXT, '
          'outcome TEXT, action TEXT, direction TEXT, reason TEXT, notified TEXT)')


def write_index(rows, path=DB_PATH, now=None):
    """Rebuild the index atomically: readers always see a complete file."""
    now = now or time.time()
    tmp = path + '.tmp'
    if os.path.exists(tmp): os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.execute(SCHEMA); db.execute('CREATE INDEX rows_ts ON rows (ts)')
    db.executemany('INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?,?,?)', [
        (r['ts'], r['qid'], r['from'], domain_of(r['from']), r['to'], domain_of(r['to']), r['outcome'], r['action'], r['direction'], r['reason'][:600], r['notified'])
        for r in rows if r['ts'] >= now - KEEP_DAYS * 86400])
    db.execute('CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)')
    db.execute('INSERT INTO meta VALUES (?,?)', ('indexed_at', str(int(now))))
    db.commit(); db.close()
    try:
        import grp
        os.chown(tmp, 0, grp.getgrnam('dmail').gr_gid)
    except (KeyError, PermissionError, ImportError, OSError):
        pass
    os.chmod(tmp, 0o640)
    os.replace(tmp, path)


class Undelivered:
    """Read side, used by the web app. A company admin (scope) only sees rows touching its domain."""
    def __init__(self, path=DB_PATH):
        self.path = path

    def query(self, scope=None, days=SHOW_DAYS, now=None, limit=500):
        now = now or time.time()
        if not os.path.exists(self.path): return {'rows': [], 'indexedAt': None, 'available': False}
        db = sqlite3.connect(f'file:{self.path}?mode=ro', uri=True, timeout=5)
        try:
            where, args = ('AND (sender_domain=? OR rcpt_domain=?)', (scope, scope)) if scope else ('', ())
            got = db.execute(f'SELECT ts,qid,sender,rcpt,outcome,action,direction,reason,notified FROM rows WHERE ts>=? {where} ORDER BY ts DESC LIMIT ?',
                             (now - days * 86400, *args, limit)).fetchall()
            at = db.execute("SELECT v FROM meta WHERE k='indexed_at'").fetchone()
        finally:
            db.close()
        keys = ('ts', 'qid', 'from', 'to', 'outcome', 'action', 'direction', 'reason', 'notified')
        return {'rows': [dict(zip(keys, r)) for r in got], 'indexedAt': int(at[0]) if at else None, 'available': True}


def main(argv):
    if len(argv) > 1 and argv[1] == '--index':
        mail, amavis = read_logs()
        rows = parse(mail, amavis)
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        write_index(rows)
        print(f'indexed {len(rows)} undelivered rows into {DB_PATH}')
        return 0
    if len(argv) > 1 and argv[1] == '--show':
        out = Undelivered().query(argv[2] if len(argv) > 2 else None)
        for r in out['rows']:
            print(time.strftime('%Y-%m-%d %H:%M', time.localtime(r['ts'])), r['outcome'], r['from'], '->', r['to'], '|', r['reason'][:90], '| told:', r['notified'])
        return 0
    print(__doc__); return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
