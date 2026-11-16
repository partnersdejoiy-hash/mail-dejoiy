"""Read-only CSV feeds of Dejoiy Mail's numbers, for live spreadsheets (Zoho Sheet "Link External Data",
Google Sheets IMPORTDATA). GET /feeds/<token>/<name>.csv on mail.dejoiy.com.

  mail.csv       mail.dejoiy.com: people, sending, sign-ins, phishing/spam, by 24h / 7d / 30d / 90d
  admin.csv      admin-mail.dejoiy.com: companies, plans, money, add-ons, help desk, integrations
  daily.csv      one row a day for the last 30 days (for charts)
  companies.csv  one row per company
  status.csv     every Dejoiy service up or down right now, and this server's health

Counts only: never mail content, passwords or keys. Subjects and addresses do not appear in any feed.
The token is in <state>/feed-token (made on first start, 0600); change or delete it to cut off old links.
"""
import csv, io, os, secrets, shutil, subprocess, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DAY = 86400
WINDOWS = (('24h', DAY), ('7d', 7 * DAY), ('30d', 30 * DAY), ('90d', 90 * DAY))
NAMES = ('mail', 'admin', 'daily', 'companies', 'status')


def token(state_dir):
    """The feed token, made once. None when the server keeps no state."""
    if not state_dir: return None
    path = Path(state_dir) / 'feed-token'
    if not path.exists():
        path.write_text(secrets.token_urlsafe(24) + '\n'); path.chmod(0o600)
    return path.read_text().strip() or None


def _cell(v):
    s = '' if v is None else str(v)
    return "'" + s if s[:1] in ('=', '+', '-', '@') and not s.lstrip('-').replace('.', '', 1).isdigit() else s   # a value never runs as a formula


def to_csv(head, rows):
    out = io.StringIO(); w = csv.writer(out, lineterminator='\r\n')
    w.writerow(head)
    for r in rows: w.writerow([_cell(v) for v in r])
    return out.getvalue()


def _q(store, sql, args=()):
    """Rows from one of the server's sqlite stores, or [] when that store is off."""
    db = getattr(store, 'db', None) if store is not None else None
    if db is None: return []
    lock = getattr(store, 'lock', None)
    if lock:
        with lock: return db.execute(sql, args).fetchall()
    return db.execute(sql, args).fetchall()


def _one(store, sql, args=()):
    rows = _q(store, sql, args)
    return rows[0][0] if rows and rows[0][0] is not None else 0


def _audit(s, kind, since, what='COUNT(*)'):
    return _one(s.audit, f'SELECT {what} FROM events WHERE kind=? AND ts>=?', (kind, since))


def _rupees(paise): return round((paise or 0) / 100, 2)


def mail(s, now=None, extra=None):
    """mail.dejoiy.com in numbers. extra: totals that need the mail server (domains, mailboxes), when it answered."""
    now = now or time.time(); rows = []
    def line(label, fn): rows.append([label] + [fn(now - span) for _, span in WINDOWS])
    line('Mails sent from the web app', lambda t: _audit(s, 'send', t, 'COALESCE(SUM(n),0)'))
    line('Messages sent (counting each send once)', lambda t: _audit(s, 'send', t))
    line('Sends refused by the mail server', lambda t: _one(s.audit, "SELECT COUNT(*) FROM events WHERE kind LIKE 'send_failed%' AND ts>=?", (t,)))
    line('Sign-ins', lambda t: _audit(s, 'signin', t))
    line('Failed sign-ins', lambda t: _audit(s, 'signin_failed', t))
    line('People active', lambda t: _one(s.audit, "SELECT COUNT(DISTINCT actor) FROM events WHERE kind IN ('send','signin') AND ts>=?", (t,)))
    line('Companies active', lambda t: _one(s.audit, "SELECT COUNT(DISTINCT domain) FROM events WHERE kind IN ('send','signin') AND ts>=?", (t,)))
    line('Phishing marked', lambda t: _one(s.security, "SELECT COUNT(*) FROM flagged WHERE level='phishing' AND at>=?", (t,)))
    line('Spam marked', lambda t: _one(s.security, "SELECT COUNT(*) FROM flagged WHERE level='suspicious' AND at>=?", (t,)))
    line('People who got phishing', lambda t: _one(s.security, "SELECT COUNT(DISTINCT mailbox) FROM flagged WHERE level='phishing' AND at>=?", (t,)))
    totals = [['Right now'], ['Signed-in sessions', getattr(s, 'live_sessions', lambda: 0)()]]
    for k, v in (extra or {}).items(): totals.append([k, v])
    totals.append(['Profile photos uploaded', _one(s.avatars, 'SELECT COUNT(*) FROM avatars')])
    totals.append(['Updated (UTC)', time.strftime('%Y-%m-%d %H:%M', time.gmtime(now))])
    return to_csv(['Metric'] + [k for k, _ in WINDOWS], rows + [[]] + totals)


def admin(s, now=None):
    """admin-mail.dejoiy.com: the business side."""
    now = now or time.time(); b = s.billing
    from billing import PLANS, SWISS, GST_PERCENT
    subs = _q(b, 'SELECT domain, plan, period, trial_ends, paid_until FROM subs')
    paid = [r for r in subs if r[4] > now]
    trial = [r for r in subs if r[4] <= now and r[3] > now]
    ended = [r for r in subs if r[4] <= now and r[3] <= now]
    monthly = lambda r: PLANS[r[1]]['month'] if r[2] == 'month' else PLANS[r[1]]['year'] / 12
    mrr = sum(monthly(r) for r in paid if r[1] in PLANS)
    addons = _one(b, 'SELECT COUNT(*) FROM addons WHERE paid_until>?', (now,))
    rows = [['COMPANIES'], ['Companies with a plan record', len(subs)], ['Paying', len(paid)], ['On free trial', len(trial)], ['Trial or plan ended', len(ended)]]
    for key, p in PLANS.items():
        rows.append([f'On {p["name"]}', sum(1 for r in paid if r[1] == key)])
    rows += [['Yearly plans', sum(1 for r in paid if r[2] == 'year')], ['Monthly plans', sum(1 for r in paid if r[2] == 'month')],
             [], ['MONEY (₹)'], ['Monthly recurring revenue, before GST', round(mrr + addons * SWISS['month'], 2)],
             [f'Monthly recurring revenue, with {GST_PERCENT}% GST', round((mrr + addons * SWISS['month']) * (1 + GST_PERCENT / 100), 2)]]
    for label, span in WINDOWS:
        got = _one(b, "SELECT COALESCE(SUM(amount*MAX(paid_count,CASE WHEN status='paid' THEN 1 ELSE 0 END)),0) FROM invoices WHERE mode='live' AND COALESCE(paid_at,created)>=?", (now - span,))
        rows.append([f'Collected, started in last {label} (with GST)', _rupees(got)])
    rows += [['Collected, all time (with GST)', _rupees(_one(b, "SELECT COALESCE(SUM(amount*MAX(paid_count,CASE WHEN status='paid' THEN 1 ELSE 0 END)),0) FROM invoices WHERE mode='live'"))],
             ['AutoPay subscriptions on', _one(b, "SELECT COUNT(*) FROM invoices WHERE status='active' AND mode='live'")],
             ['Payments waiting', _one(b, "SELECT COUNT(*) FROM invoices WHERE status='created'")],
             [], ['ADD-ONS AND SENDING'], ['Swiss Mail add-ons paid', addons],
             ['Companies with their own mail service', sum(1 for c in (getattr(s.relays, 'all', {}) or {}).values() if c.get('active') and c.get('kind') != 'swiss')],
             ['Companies with a Swiss Mail key', sum(1 for c in (getattr(s.relays, 'all', {}) or {}).values() if c.get('kind') == 'swiss')],
             [], ['HELP DESK AND ADMIN'],
             ['Open tickets', _one(s.tickets, "SELECT COUNT(*) FROM tickets WHERE status NOT IN ('resolved','closed')")],
             ['Tickets opened, last 30d', _one(s.tickets, 'SELECT COUNT(*) FROM tickets WHERE created>=?', (int(now - 30 * DAY),))],
             ['Overdue tickets', _one(s.tickets, "SELECT COUNT(*) FROM tickets WHERE status NOT IN ('resolved','closed') AND due<?", (int(now),))],
             ['Admin changes, last 7d', _one(s.audit, "SELECT COUNT(*) FROM events WHERE kind LIKE 'admin%' AND ts>=?", (now - 7 * DAY,))],
             ['Admin changes, last 30d', _one(s.audit, "SELECT COUNT(*) FROM events WHERE kind LIKE 'admin%' AND ts>=?", (now - 30 * DAY,))],
             ['API calls (company tokens), last 30d', _one(s.audit, "SELECT COUNT(*) FROM events WHERE kind LIKE 'api:%' AND ts>=?", (now - 30 * DAY,))],
             ['Updated (UTC)', time.strftime('%Y-%m-%d %H:%M', time.gmtime(now))]]
    return to_csv(['Metric', 'Value'], rows)


def daily(s, now=None, days=30):
    now = now or time.time()
    out = []
    for i in range(days - 1, -1, -1):
        start = (int(now) // DAY - i) * DAY; end = start + DAY
        ev = lambda kind, what='COUNT(*)': _one(s.audit, f'SELECT {what} FROM events WHERE kind=? AND ts>=? AND ts<?', (kind, start, end))
        out.append([time.strftime('%Y-%m-%d', time.gmtime(start)), ev('send', 'COALESCE(SUM(n),0)'), ev('signin'), ev('signin_failed'),
                    _one(s.audit, "SELECT COUNT(DISTINCT actor) FROM events WHERE kind IN ('send','signin') AND ts>=? AND ts<?", (start, end)),
                    _one(s.security, "SELECT COUNT(*) FROM flagged WHERE level='phishing' AND at>=? AND at<?", (start, end)),
                    _one(s.security, "SELECT COUNT(*) FROM flagged WHERE level='suspicious' AND at>=? AND at<?", (start, end)),
                    _rupees(_one(s.billing, "SELECT COALESCE(SUM(amount),0) FROM invoices WHERE mode='live' AND paid_at>=? AND paid_at<?", (start, end)))])
    return to_csv(['Date (UTC)', 'Mails sent', 'Sign-ins', 'Failed sign-ins', 'People active', 'Phishing', 'Spam', 'First payments (₹)'], out)


def companies(s, now=None, mailboxes=None):
    """One row per company. mailboxes: {domain: count} when the mail server answered."""
    now = now or time.time(); since = now - 30 * DAY
    plans = {r[0]: r for r in _q(s.billing, 'SELECT domain, plan, period, trial_ends, paid_until FROM subs')}
    addons = {r[0]: r[1] for r in _q(s.billing, 'SELECT domain, paid_until FROM addons')}
    sent = dict(_q(s.audit, "SELECT domain, COALESCE(SUM(n),0) FROM events WHERE kind='send' AND ts>=? GROUP BY domain", (since,)))
    people = dict(_q(s.audit, "SELECT domain, COUNT(DISTINCT actor) FROM events WHERE kind IN ('send','signin') AND ts>=? GROUP BY domain", (since,)))
    phish = dict(_q(s.security, "SELECT domain, COUNT(*) FROM flagged WHERE level='phishing' AND at>=? GROUP BY domain", (since,)))
    spam = dict(_q(s.security, "SELECT domain, COUNT(*) FROM flagged WHERE level='suspicious' AND at>=? GROUP BY domain", (since,)))
    relays = getattr(s.relays, 'all', {}) or {}
    reserved = getattr(s, 'reserved_domains', set())
    names = sorted(set(plans) | set(sent) | set(people) | set(mailboxes or {}))
    rows = []
    for d in names:
        if not d: continue
        p = plans.get(d); own = any(d == r or d.endswith('.' + r) for r in reserved)
        state = 'Dejoiy' if own else 'paying' if p and p[4] > now else 'trial' if p and p[3] > now else 'ended' if p else '—'
        cfg = relays.get(d) or {}
        rows.append([d, state, (p[1] or '') if p else '', (p[2] or '') if p else '',
                     time.strftime('%Y-%m-%d', time.gmtime(p[4] if p[4] > now else p[3])) if p else '',
                     (mailboxes or {}).get(d, ''), people.get(d, 0), sent.get(d, 0), phish.get(d, 0), spam.get(d, 0),
                     'yes' if addons.get(d, 0) > now else '', 'Swiss Mail' if cfg.get('kind') == 'swiss' else cfg.get('host', '') if cfg.get('active') else ''])
    return to_csv(['Company', 'State', 'Plan', 'Period', 'Paid or trial until', 'Mailboxes', 'People active 30d', 'Mails sent 30d',
                   'Phishing 30d', 'Spam 30d', 'Swiss add-on', 'Own mail service'], rows)


# ---------- live status ----------
# Name|URL pairs; STATUS_CHECKS (comma-separated, same form) replaces them. Up = it answered below 500.
CHECKS = (('Dejoiy Mail (mail.dejoiy.com)', 'https://mail.dejoiy.com/api/config'),
          ('Dejoiy Mail Admin (admin-mail.dejoiy.com)', 'https://admin-mail.dejoiy.com/'),
          ('Shine app (app.shine.dejoiy.com)', 'https://app.shine.dejoiy.com/'),
          ('Shine backend (convex-site.shine.dejoiy.com)', 'https://convex-site.shine.dejoiy.com/'),
          ('Swiss Mail API', 'https://nvxvtkwmqmoycptznefs.supabase.co/functions/v1/api/health'),
          ('Dejoiy Pay (pay.dejoiy.com)', 'https://pay.dejoiy.com/'),
          ('dejoiy.com', 'https://dejoiy.com/'))
SLOW_MS = 2000


def checks():
    raw = os.environ.get('STATUS_CHECKS', '').strip()
    if not raw: return CHECKS
    return tuple(tuple(x.split('|', 1)) for x in raw.split(',') if '|' in x)


def probe(url, timeout=8, opener=None):
    """(state, milliseconds, http code) for one address."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'DejoiyStatus/1.0'})
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r: code = r.status
    except urllib.error.HTTPError as e: code = e.code
    except Exception: return 'DOWN', int((time.monotonic() - start) * 1000), ''
    ms = int((time.monotonic() - start) * 1000)
    return ('DOWN' if code >= 500 else 'SLOW' if ms > SLOW_MS else 'UP'), ms, code


def server_health(state_dir='/', zimbra_ok=None):
    """This server's own numbers: disk, memory, load, uptime, mail queue, the mail system."""
    rows = []
    try:
        d = shutil.disk_usage(state_dir or '/'); rows.append(['Disk used', f'{d.used / d.total * 100:.0f}%', f'{d.free / 2**30:.1f} GB free'])
    except OSError: pass
    try:
        mem = dict(l.split(':', 1) for l in Path('/proc/meminfo').read_text().splitlines() if ':' in l)
        total, avail = int(mem['MemTotal'].split()[0]), int(mem['MemAvailable'].split()[0])
        rows.append(['Memory used', f'{(total - avail) / total * 100:.0f}%', f'{avail / 2**20:.1f} GB free'])
    except (OSError, KeyError, ValueError): pass
    try:
        one, five, _ = os.getloadavg(); rows.append(['CPU load (1 min / 5 min)', f'{one:.2f}', f'{five:.2f} · {os.cpu_count()} CPUs'])
    except OSError: pass
    try: rows.append(['Up for', f'{float(Path("/proc/uptime").read_text().split()[0]) / 86400:.1f} days', ''])
    except (OSError, ValueError): pass
    try:
        out = subprocess.run(['/opt/zimbra/common/sbin/postqueue', '-j'], capture_output=True, text=True, timeout=10)
        if out.returncode == 0: rows.append(['Mails waiting in the queue', str(sum(1 for l in out.stdout.splitlines() if l.strip())), ''])
    except (OSError, subprocess.SubprocessError): pass
    if zimbra_ok is not None: rows.append(['Mail system (Zimbra) answering', 'UP' if zimbra_ok else 'DOWN', ''])
    return rows


def status(state_dir=None, zimbra_ok=None, opener=None, now=None):
    now = now or time.time(); stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))
    todo = checks()
    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:
        found = list(pool.map(lambda c: probe(c[1], opener=opener), todo))
    rows = [[name, *res, stamp] for (name, _), res in zip(todo, found)]
    up = sum(1 for r in rows if r[1] != 'DOWN')
    rows += [[], ['Services up', f'{up} of {len(rows)}', '', '', stamp], [], ['THIS SERVER', 'Value', 'More', '', '']]
    rows += [[*r, '', ''] for r in server_health(state_dir, zimbra_ok)]
    return to_csv(['Service', 'Status', 'Response (ms)', 'HTTP', 'Checked (UTC)'], rows)
