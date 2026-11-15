"""Subscriptions for Dejoiy Mail (Shine comes with every plan), paid through Dejoiy Pay (pay.dejoiy.com).

A company is on an 11-day free trial from the first time its billing is looked at (or from sign-up).
An admin picks a plan and monthly or yearly; this server asks Dejoiy Pay for a payment link with
the price plus 18% GST and sends the admin there. The plan starts when Dejoiy Pay says the link is
paid: either its signed webhook arrives here, or the billing page asks Dejoiy Pay directly.

Standard library only. Settings (in /etc/dmail/adapter.env):
    DEJOIY_PAY_KEY_ID, DEJOIY_PAY_KEY_SECRET   an API key from pay.dejoiy.com, Developers > API keys
    DEJOIY_PAY_WEBHOOK_SECRET                  the secret of the webhook pointing at /api/pay/webhook
    DEJOIY_PAY_URL                             optional, default https://pay.dejoiy.com
Nothing here ever holds card or bank details: the customer pays on pay.dejoiy.com.
"""
import base64, hashlib, hmac, json, secrets, sqlite3, threading, time, urllib.error, urllib.request

# rupees before GST; must match the pricing on the home page (web/home.html, web/js/signup.js)
PLANS = {
    'starter': {'name': 'Starter', 'month': 99, 'year': 790, 'mailboxes': 51},
    'team': {'name': 'Team', 'month': 299, 'year': 2490, 'mailboxes': 101},
    'business': {'name': 'Business', 'month': 699, 'year': 5990, 'mailboxes': None},
}
GST_PERCENT = 18
TRIAL_DAYS = 11
DAY = 86400
PERIOD_DAYS = {'month': 30, 'year': 365}
LINK_HOURS = 48
# The Swiss Mail add-on: a company's own reputation-safe sending through Dejoiy Swiss Mail (rupees before GST, a month)
SWISS = {'name': 'Swiss Mail add-on', 'month': 199, 'mails': 10_000}


class BillingError(ValueError):
    """Something the admin can fix or should know; the message is safe to show."""


def price_paise(plan, period):
    """What the customer pays, GST included, in paise (Dejoiy Pay's unit)."""
    rupees = SWISS['month'] if plan == 'swiss' else PLANS[plan][period]
    return rupees * 100 + (rupees * 100 * GST_PERCENT + 50) // 100


class DejoiyPay:
    """The few Dejoiy Pay REST calls billing needs (HTTP Basic auth with the API key)."""
    def __init__(self, url, key_id, key_secret, opener=None):
        self.url = url.rstrip('/'); self.key_id = key_id; self.key_secret = key_secret
        self.opener = opener or urllib.request.urlopen

    @property
    def mode(self):
        return 'live' if self.key_id.startswith('dp_live_') else 'test'

    def call(self, method, path, body=None):
        auth = base64.b64encode(f'{self.key_id}:{self.key_secret}'.encode()).decode()
        request = urllib.request.Request(self.url + '/api/v1' + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json', 'User-Agent': 'DejoiyMail-Billing'})
        try:
            with self.opener(request, timeout=20) as response:
                return json.loads(response.read() or b'{}')
        except urllib.error.HTTPError as e:
            try: why = json.loads(e.read() or b'{}').get('error', {}).get('description')
            except (ValueError, AttributeError): why = None
            raise BillingError(f'Dejoiy Pay said no: {why or e.code}.')
        except (urllib.error.URLError, OSError, ValueError):
            raise BillingError('Dejoiy Pay could not be reached. Try again in a minute.')

    def create_link(self, **fields): return self.call('POST', '/payment_links', fields)
    def link(self, link_id): return self.call('GET', '/payment_links/' + link_id)
    def create_subscription(self, **fields): return self.call('POST', '/subscriptions', fields)
    def subscription(self, sub_id): return self.call('GET', '/subscriptions/' + sub_id)
    def cancel_subscription(self, sub_id): return self.call('POST', '/subscriptions/' + sub_id + '/cancel', {})


class Billing:
    def __init__(self, path, pay=None, webhook_secret='', clock=time.time):
        self.pay = pay; self.webhook_secret = webhook_secret; self.clock = clock; self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS subs (domain TEXT PRIMARY KEY, plan TEXT, period TEXT, trial_ends REAL NOT NULL, paid_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS invoices (link_id TEXT PRIMARY KEY, domain TEXT NOT NULL, plan TEXT NOT NULL, period TEXT NOT NULL,
                amount INTEGER NOT NULL, mode TEXT NOT NULL, url TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
                paid_at REAL, payment_id TEXT, by TEXT);
            CREATE INDEX IF NOT EXISTS invoices_domain ON invoices(domain, created);
            CREATE TABLE IF NOT EXISTS addons (domain TEXT PRIMARY KEY, paid_until REAL NOT NULL DEFAULT 0);''')
        try: self.db.execute('ALTER TABLE invoices ADD COLUMN paid_count INTEGER NOT NULL DEFAULT 0')   # auto-renewing subscriptions: charges so far
        except sqlite3.OperationalError: pass
        if pay is not None and pay.mode == 'live': self._leave_test()
        self.db.commit()

    def _leave_test(self):
        """Switched to a live key: test payments were never real, so they stop counting. Test subscriptions
        can't be seen with a live key either, so they no longer block subscribing for real."""
        test_domains = [r[0] for r in self.db.execute("SELECT DISTINCT domain FROM invoices WHERE mode='test' AND status IN ('created','active','cancelling','paid')")]
        for domain in test_domains:
            real = self.db.execute("SELECT 1 FROM invoices WHERE domain=? AND mode='live' AND (status IN ('active','cancelling','paid'))", (domain,)).fetchone()
            if not real:
                self.db.execute('UPDATE subs SET paid_until=0, plan=NULL, period=NULL WHERE domain=?', (domain,))
                self.db.execute('UPDATE addons SET paid_until=0 WHERE domain=?', (domain,))
        self.db.execute("UPDATE invoices SET status='test' WHERE mode='test' AND status IN ('created','active','cancelling','paid','replaced')")

    @property
    def ready(self): return self.pay is not None

    def _sub(self, domain):
        row = self.db.execute('SELECT plan, period, trial_ends, paid_until FROM subs WHERE domain=?', (domain,)).fetchone()
        if row: return {'plan': row[0], 'period': row[1], 'trial_ends': row[2], 'paid_until': row[3]}
        sub = {'plan': None, 'period': None, 'trial_ends': self.clock() + TRIAL_DAYS * DAY, 'paid_until': 0}
        self.db.execute('INSERT INTO subs (domain, trial_ends) VALUES (?, ?)', (domain, sub['trial_ends'])); self.db.commit()
        return sub

    def start_trial(self, domain):
        """A new company (sign-up finished): its 11 days start now."""
        with self.lock: self._sub(domain)

    def status(self, domain):
        """What the billing page shows. Asks Dejoiy Pay about links still open, so a payment shows up
        even before (or without) the webhook."""
        self.refresh(domain)
        with self.lock:
            sub = self._sub(domain); now = self.clock()
            rows = self.db.execute("SELECT link_id, plan, period, amount, mode, url, status, created, paid_at, paid_count FROM invoices WHERE domain=? AND plan!='swiss' ORDER BY created DESC LIMIT 12", (domain,)).fetchall()
        if sub['paid_until'] > now: state, ends = 'active', sub['paid_until']
        elif sub['trial_ends'] > now and not sub['paid_until']: state, ends = 'trial', sub['trial_ends']
        else: state, ends = 'expired', max(sub['paid_until'], sub['trial_ends'])
        invoices = [{'id': r[0], 'plan': r[1], 'period': r[2], 'amount': r[3], 'mode': r[4], 'url': r[5], 'status': r[6], 'created': int(r[7]), 'paidAt': int(r[8]) if r[8] else None,
                     'auto': r[0].startswith('sub_'), 'charges': r[9]} for r in rows]
        plan = PLANS.get(sub['plan'] or '')
        return {'state': state, 'ends': int(ends), 'daysLeft': max(0, int((ends - now + DAY - 1) // DAY)),
                'plan': sub['plan'], 'planName': plan['name'] if plan else None, 'period': sub['period'],
                'mailboxes': plan['mailboxes'] if plan else None, 'invoices': invoices,
                'open': next((i for i in invoices if i['status'] == 'created'), None),
                'renewing': next((i for i in invoices if i['status'] == 'active'), None),
                'payReady': self.ready, 'payMode': self.pay.mode if self.pay else None,
                'plans': [{'id': k, **v, 'monthPaise': price_paise(k, 'month'), 'yearPaise': price_paise(k, 'year')} for k, v in PLANS.items()],
                'gst': GST_PERCENT}

    def checkout(self, domain, plan, period, email, name='', by=''):
        """An auto-renewing subscription on Dejoiy Pay: the admin authorises UPI AutoPay or a card once,
        then every month or year is charged by itself until they turn auto-renew off."""
        if not self.ready: raise BillingError('Payments are not switched on for this server yet.')
        if plan not in PLANS or period not in PERIOD_DAYS: raise BillingError('Pick a plan and monthly or yearly.')
        with self.lock:
            renewing = self.db.execute("SELECT plan, period FROM invoices WHERE domain=? AND status=? AND plan!='swiss'", (domain, 'active')).fetchone()
        if renewing: raise BillingError(f'{PLANS[renewing[0]]["name"]} ({"yearly" if renewing[1] == "year" else "monthly"}) already renews by itself. Turn auto-renew off first to change plan.')
        amount = price_paise(plan, period)
        p = PLANS[plan]
        sub = self.pay.create_subscription(
            plan={'name': f'Dejoiy Mail + Shine · {p["name"]} ({"yearly" if period == "year" else "monthly"})', 'amount': amount, 'period': 'yearly' if period == 'year' else 'monthly'},
            customer={k: v for k, v in (('email', email), ('name', name)) if v}, reference_id=f'dm-{secrets.token_hex(6)}',
            notes={'domain': domain, 'plan': plan, 'period': period, 'product': 'dejoiy-mail'})
        sub_id, url = str(sub.get('id') or ''), str(sub.get('short_url') or '')
        if not sub_id.startswith('sub_') or not url.startswith('https://'): raise BillingError('Dejoiy Pay sent back something unexpected. Try again.')
        with self.lock:
            self._sub(domain)
            # one waiting payment at a time: an older unpaid one is left to expire on its own
            self.db.execute("UPDATE invoices SET status=? WHERE domain=? AND status=? AND plan!='swiss'", ('replaced', domain, 'created'))
            self.db.execute('INSERT INTO invoices (link_id, domain, plan, period, amount, mode, url, status, created, by) VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (sub_id, domain, plan, period, amount, str(sub.get('mode') or self.pay.mode), url, 'created', self.clock(), by))
            self.db.commit()
        return {'url': url, 'id': sub_id, 'amount': amount}

    def cancel(self, domain):
        """Turn auto-renew off: nothing more is charged, the time already paid runs out."""
        with self.lock:
            row = self.db.execute("SELECT link_id FROM invoices WHERE domain=? AND status=? AND plan!='swiss'", (domain, 'active')).fetchone()
        if not row: raise BillingError('Nothing renews by itself right now.')
        self._apply_subscription(row[0], self.pay.cancel_subscription(row[0]))
        return {'ok': True}

    def _apply_subscription(self, sub_id, sub):
        """Dejoiy Pay's view of one subscription: paid until current_end, renewing or not."""
        status, end = sub.get('status'), sub.get('current_end')
        mine = 'active' if status in ('active', 'authenticated') and sub.get('auto_renew', True) else \
               'cancelling' if status in ('active', 'authenticated') else \
               'created' if status == 'created' else 'ended'
        with self.lock:
            row = self.db.execute('SELECT domain, plan, period, status FROM invoices WHERE link_id=?', (sub_id,)).fetchone()
            if not row: return False
            domain, plan, period, before = row
            self.applied = (domain, plan)   # which company and product the last update was for
            if before == 'replaced' and mine == 'created': return False
            paid = sub.get('paid_count') or 0
            self.db.execute('UPDATE invoices SET status=?, paid_count=?, paid_at=COALESCE(paid_at, ?) WHERE link_id=?', (mine, paid, self.clock() if paid else None, sub_id))
            if paid and end and plan == 'swiss':
                self.db.execute('INSERT INTO addons (domain, paid_until) VALUES (?, ?) ON CONFLICT(domain) DO UPDATE SET paid_until=MAX(paid_until, excluded.paid_until)', (domain, float(end)))
            elif paid and end:
                cur = self._sub(domain)
                self.db.execute('UPDATE subs SET plan=?, period=?, paid_until=? WHERE domain=?', (plan, period, max(cur['paid_until'], float(end)), domain))
            self.db.commit()
            return bool(paid)

    def refresh(self, domain):
        """Ask Dejoiy Pay about this company's open links and subscriptions (cheap: at most three)."""
        if not self.ready: return
        with self.lock:
            open_ = [r[0] for r in self.db.execute('SELECT link_id FROM invoices WHERE domain=? AND status IN (?,?,?,?) ORDER BY created DESC LIMIT 5', (domain, 'created', 'replaced', 'active', 'cancelling'))]
        for link_id in open_:
            try:
                if link_id.startswith('sub_'):
                    self._apply_subscription(link_id, self.pay.subscription(link_id)); continue
                link = self.pay.link(link_id)
            except BillingError: return   # Dejoiy Pay is away; the page shows what we know
            if link.get('status') == 'paid': self.paid(link_id)
            elif link.get('status') in ('cancelled', 'expired'):
                with self.lock:
                    self.db.execute('UPDATE invoices SET status=? WHERE link_id=? AND status IN (?,?)', (link['status'], link_id, 'created', 'replaced')); self.db.commit()

    # ---- the Swiss Mail add-on: its own monthly AutoPay subscription, next to the plan ----
    def addon_until(self, domain):
        """Until when the add-on is paid, from what is stored here (no call to Dejoiy Pay: used on every send)."""
        with self.lock: row = self.db.execute('SELECT paid_until FROM addons WHERE domain=?', (domain,)).fetchone()
        return row[0] if row else 0

    def addon(self, domain):
        """Whether the company's Swiss Mail add-on is paid for now, and what the page shows about it."""
        self.refresh(domain)
        with self.lock:
            row = self.db.execute('SELECT paid_until FROM addons WHERE domain=?', (domain,)).fetchone()
            subs = self.db.execute("SELECT link_id, amount, url, status, mode, paid_count FROM invoices WHERE domain=? AND plan='swiss' ORDER BY created DESC LIMIT 6", (domain,)).fetchall()
        until = row[0] if row else 0
        pick = lambda status: next(({'id': r[0], 'amount': r[1], 'url': r[2], 'mode': r[4], 'charges': r[5]} for r in subs if r[3] == status), None)
        return {'active': until > self.clock(), 'paidUntil': int(until), 'renewing': pick('active'), 'open': pick('created'),
                'price': SWISS['month'], 'pricePaise': price_paise('swiss', 'month'), 'mails': SWISS['mails'], 'gst': GST_PERCENT,
                'payReady': self.ready, 'payMode': self.pay.mode if self.pay else None}

    def addon_checkout(self, domain, email, name='', by=''):
        if not self.ready: raise BillingError('Payments are not switched on for this server yet.')
        with self.lock:
            if self.db.execute("SELECT 1 FROM invoices WHERE domain=? AND plan='swiss' AND status='active'", (domain,)).fetchone():
                raise BillingError('The Swiss Mail add-on already renews by itself.')
        amount = price_paise('swiss', 'month')
        sub = self.pay.create_subscription(
            plan={'name': f'Dejoiy Swiss Mail add-on · {SWISS["mails"]:,} mails a month', 'amount': amount, 'period': 'monthly'},
            customer={k: v for k, v in (('email', email), ('name', name)) if v}, reference_id=f'dms-{secrets.token_hex(6)}',
            notes={'domain': domain, 'plan': 'swiss', 'period': 'month', 'product': 'dejoiy-swiss-mail'})
        sub_id, url = str(sub.get('id') or ''), str(sub.get('short_url') or '')
        if not sub_id.startswith('sub_') or not url.startswith('https://'): raise BillingError('Dejoiy Pay sent back something unexpected. Try again.')
        with self.lock:
            self.db.execute("UPDATE invoices SET status='replaced' WHERE domain=? AND status='created' AND plan='swiss'", (domain,))
            self.db.execute('INSERT INTO invoices (link_id, domain, plan, period, amount, mode, url, status, created, by) VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (sub_id, domain, 'swiss', 'month', amount, str(sub.get('mode') or self.pay.mode), url, 'created', self.clock(), by))
            self.db.commit()
        return {'url': url, 'id': sub_id, 'amount': amount}

    def addon_cancel(self, domain):
        with self.lock:
            row = self.db.execute("SELECT link_id FROM invoices WHERE domain=? AND plan='swiss' AND status='active'", (domain,)).fetchone()
        if not row: raise BillingError('The add-on does not renew by itself right now.')
        self._apply_subscription(row[0], self.pay.cancel_subscription(row[0]))
        return {'ok': True}

    def paid(self, link_id, payment_id=None, amount=None):
        """Dejoiy Pay says this link is paid: start or extend the plan. Safe to call twice."""
        with self.lock:
            row = self.db.execute('SELECT domain, plan, period, amount, status FROM invoices WHERE link_id=?', (link_id,)).fetchone()
            if not row or row[4] == 'paid': return False
            domain, plan, period, due, _ = row
            if amount is not None and amount < due: return False   # a part payment does not buy a plan
            sub = self._sub(domain); now = self.clock()
            start = max(now, sub['paid_until'], sub['trial_ends'] if not sub['paid_until'] else 0)   # trial days left are kept
            self.db.execute('UPDATE subs SET plan=?, period=?, paid_until=? WHERE domain=?', (plan, period, start + PERIOD_DAYS[period] * DAY, domain))
            self.db.execute('UPDATE invoices SET status=?, paid_at=?, payment_id=? WHERE link_id=?', ('paid', now, payment_id, link_id))
            self.db.commit()
            return True

    def webhook(self, raw, signature):
        """POST /api/pay/webhook from Dejoiy Pay: a signed note that a payment went through."""
        if not self.webhook_secret: raise BillingError('Webhook secret is not set on this server.')
        mac = hmac.new(self.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, (signature or '').strip().lower()): raise BillingError('Bad signature.')
        try: note = json.loads(raw)
        except ValueError: raise BillingError('Not JSON.')
        payment = note.get('payload') if isinstance(note, dict) else None
        if note.get('event') != 'payment.captured' or not isinstance(payment, dict): return {'ok': True, 'used': False}
        if payment.get('source') == 'subscription' and str(payment.get('source_id', '')).startswith('sub_'):
            # a first charge or a renewal: Dejoiy Pay is asked for the subscription's paid period
            sub_id = payment['source_id']; self.applied = (None, None)
            used = bool(self.ready and self._apply_subscription(sub_id, self.pay.subscription(sub_id)))
            return {'ok': True, 'used': used, **({'domain': self.applied[0], 'plan': self.applied[1]} if used else {})}
        if payment.get('source') != 'link' or not str(payment.get('source_id', '')).startswith('plink_'): return {'ok': True, 'used': False}
        # the webhook only says which link; Dejoiy Pay itself is asked whether that link is now fully paid
        link_id = payment['source_id']
        if self.ready:
            link = self.pay.link(link_id)
            if link.get('status') != 'paid': return {'ok': True, 'used': False}
        return {'ok': True, 'used': self.paid(link_id, str(payment.get('id') or '') or None)}
