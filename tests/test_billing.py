"""Subscriptions paid through Dejoiy Pay, against a fake Dejoiy Pay (no network)."""
import hashlib, hmac, io, json, os, sys, tempfile, unittest, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import billing as b

DAY = 86400


class FakePay:
    """Dejoiy Pay's subscription API, as far as billing uses it."""
    mode = 'test'
    def __init__(self, clock): self.subs = {}; self.made = []; self.clock = clock
    def create_subscription(self, **fields):
        self.made.append(fields); sub_id = f'sub_{len(self.made)}'
        self.subs[sub_id] = {'id': sub_id, 'status': 'created', 'auto_renew': True, 'paid_count': 0, 'current_end': None, 'short_url': f'https://pay.dejoiy.com/s/c{len(self.made)}', 'mode': 'test', 'period': fields['plan']['period']}
        return dict(self.subs[sub_id])
    def subscription(self, sub_id): return dict(self.subs[sub_id])
    def cancel_subscription(self, sub_id):
        self.subs[sub_id]['auto_renew'] = False; return dict(self.subs[sub_id])
    def charge(self, sub_id):
        """The first payment, or a renewal done by AutoPay."""
        s = self.subs[sub_id]; start = s['current_end'] or self.clock()
        s.update(status='active', paid_count=s['paid_count'] + 1, current_end=start + (365 if s['period'] == 'yearly' else 30) * DAY)


class Clock:
    def __init__(self): self.t = 1_800_000_000.0
    def __call__(self): return self.t


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.pay = FakePay(self.clock)
        self.bill = b.Billing(os.path.join(tempfile.mkdtemp(), 'billing.sqlite'), self.pay, 'whsec', clock=self.clock)

    def test_prices_include_gst_and_match_the_home_page(self):
        self.assertEqual(b.price_paise('starter', 'month'), 11682)      # ₹99 + 18%
        self.assertEqual(b.price_paise('business', 'year'), 706820)     # ₹5,990 + 18%
        home = open(os.path.join(os.path.dirname(__file__), '..', 'web', 'js', 'signup.js')).read()
        for key, p in b.PLANS.items(): self.assertIn(f'{key}:["{p["name"]}",{p["month"]},{p["year"]}', home)

    def test_subscription_renews_by_itself_until_cancelled(self):
        s = self.bill.status('kaali.in')
        self.assertEqual((s['state'], s['daysLeft']), ('trial', 11))
        out = self.bill.checkout('kaali.in', 'team', 'month', 'boss@kaali.in', 'Boss')
        made = self.pay.made[0]
        self.assertEqual((made['plan']['amount'], made['plan']['period'], made['notes']['domain']), (b.price_paise('team', 'month'), 'monthly', 'kaali.in'))
        self.assertTrue(out['url'].startswith('https://pay.dejoiy.com/'))
        self.assertEqual(self.bill.status('kaali.in')['open']['id'], out['id'])
        self.pay.charge(out['id'])                                     # first payment + AutoPay mandate
        s = self.bill.status('kaali.in')
        self.assertEqual((s['state'], s['plan'], s['period'], s['daysLeft']), ('active', 'team', 'month', 30))
        self.assertEqual(s['renewing']['id'], out['id']); self.assertIsNone(s['open'])
        self.clock.t += 30 * DAY; self.pay.charge(out['id'])           # a month later AutoPay charges again
        self.assertEqual(self.bill.status('kaali.in')['daysLeft'], 30)
        with self.assertRaisesRegex(b.BillingError, 'already renews'): self.bill.checkout('kaali.in', 'business', 'year', 'boss@kaali.in')
        self.bill.cancel('kaali.in')
        s = self.bill.status('kaali.in')
        self.assertEqual((s['state'], s['renewing']), ('active', None))  # paid time runs out, nothing more is charged
        self.clock.t += 31 * DAY
        self.assertEqual(self.bill.status('kaali.in')['state'], 'expired')

    def test_unpaid_subscription_buys_nothing(self):
        self.bill.checkout('kaali.in', 'starter', 'month', 'a@kaali.in')
        self.clock.t += 12 * DAY
        self.assertEqual(self.bill.status('kaali.in')['state'], 'expired')

    def test_webhook_needs_signature_and_asks_dejoiy_pay(self):
        out = self.bill.checkout('kaali.in', 'team', 'month', 'a@kaali.in')
        note = json.dumps({'event': 'payment.captured', 'payload': {'id': 'pay_1', 'source': 'subscription', 'source_id': out['id'], 'amount': 35282}}).encode()
        sign = lambda raw, key='whsec': hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()
        with self.assertRaises(b.BillingError): self.bill.webhook(note, sign(note, 'wrong'))
        self.assertFalse(self.bill.webhook(note, sign(note))['used'])      # Dejoiy Pay says nothing is paid yet
        self.pay.charge(out['id'])
        self.assertTrue(self.bill.webhook(note, sign(note))['used'])
        self.assertEqual(self.bill.status('kaali.in')['state'], 'active')
        other = json.dumps({'event': 'payment.failed', 'payload': {}}).encode()
        self.assertFalse(self.bill.webhook(other, sign(other))['used'])

    def test_switching_to_a_live_key_drops_test_payments(self):
        out = self.bill.checkout('kaali.in', 'team', 'month', 'a@kaali.in'); self.pay.charge(out['id'])
        self.assertEqual(self.bill.status('kaali.in')['renewing']['id'], out['id'])
        self.pay.mode = 'live'
        live = b.Billing(self.bill.db.execute('PRAGMA database_list').fetchone()[2], self.pay, 'whsec', clock=self.clock)
        s = live.status('kaali.in')
        self.assertIsNone(s['renewing']); self.assertEqual(s['state'], 'trial'); self.assertEqual(s['invoices'][0]['status'], 'test')
        live.checkout('kaali.in', 'team', 'month', 'a@kaali.in')        # not blocked any more

    def test_bad_choice_and_no_keys(self):
        with self.assertRaises(b.BillingError): self.bill.checkout('kaali.in', 'gold', 'month', 'a@kaali.in')
        off = b.Billing(os.path.join(tempfile.mkdtemp(), 'b.sqlite'))
        self.assertFalse(off.status('x.in')['payReady'])
        with self.assertRaises(b.BillingError): off.checkout('x.in', 'team', 'month', 'a@x.in')


class DejoiyPayClient(unittest.TestCase):
    def test_basic_auth_and_errors_are_readable(self):
        seen = {}
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): pass
        def opener(request, timeout):
            seen['auth'] = request.headers['Authorization']; seen['url'] = request.full_url
            if request.get_method() == 'GET':
                raise urllib.error.HTTPError(request.full_url, 404, 'nf', {}, io.BytesIO(b'{"error":{"description":"no such link"}}'))
            return Resp(b'{"id":"plink_x","short_url":"https://pay.dejoiy.com/pay/x"}')
        pay = b.DejoiyPay('https://pay.dejoiy.com/', 'dp_test_k', 's3cret', opener)
        self.assertEqual(pay.create_link(title='t', amount=100)['id'], 'plink_x')
        self.assertEqual(seen['url'], 'https://pay.dejoiy.com/api/v1/payment_links')
        self.assertEqual(seen['auth'], 'Basic ZHBfdGVzdF9rOnMzY3JldA==')
        with self.assertRaisesRegex(b.BillingError, 'no such link'): pay.link('plink_y')
        self.assertEqual(pay.mode, 'test')


if __name__ == '__main__': unittest.main()


class ShineSend(unittest.TestCase):
    def test_plain_mail_goes_to_the_local_mail_system(self):
        import smtpd_stub
        got = smtpd_stub.run(lambda port: __import__('zimbra').send_plain_mail('Shine <no-reply@mail.dejoiy.com>', 'a@b.in', 'Your code', '123456', '<b>123456</b>', host='127.0.0.1', port=port))
        self.assertIn('Subject: Your code', got); self.assertIn('To: a@b.in', got); self.assertIn('<b>123456</b>', got)


class SwissAddon(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.pay = FakePay(self.clock)
        self.bill = b.Billing(os.path.join(tempfile.mkdtemp(), 'billing.sqlite'), self.pay, 'whsec', clock=self.clock)

    def test_addon_renews_on_its_own_and_does_not_touch_the_plan(self):
        self.assertFalse(self.bill.addon('kaali.in')['active'])
        plan = self.bill.checkout('kaali.in', 'team', 'month', 'a@kaali.in'); self.pay.charge(plan['id'])
        out = self.bill.addon_checkout('kaali.in', 'a@kaali.in')
        self.assertEqual(self.pay.made[-1]['plan']['amount'], 23482)                  # ₹199 + 18%
        self.assertEqual(self.bill.addon('kaali.in')['open']['id'], out['id'])
        self.pay.charge(out['id'])
        ad = self.bill.addon('kaali.in')
        self.assertTrue(ad['active']); self.assertEqual(ad['renewing']['id'], out['id'])
        self.assertEqual(self.bill.addon_until('kaali.in'), self.clock.t + 30 * DAY)
        s = self.bill.status('kaali.in')
        self.assertEqual((s['plan'], s['renewing']['id']), ('team', plan['id']))       # the plan is its own subscription
        self.assertTrue(all(i['plan'] != 'swiss' for i in s['invoices']))
        with self.assertRaisesRegex(b.BillingError, 'already renews'): self.bill.addon_checkout('kaali.in', 'a@kaali.in')
        self.bill.addon_cancel('kaali.in')
        self.assertIsNone(self.bill.addon('kaali.in')['renewing'])
        self.clock.t += 31 * DAY
        self.assertFalse(self.bill.addon('kaali.in')['active'])

    def test_webhook_says_which_company_and_product(self):
        out = self.bill.addon_checkout('kaali.in', 'a@kaali.in'); self.pay.charge(out['id'])
        note = json.dumps({'event': 'payment.captured', 'payload': {'id': 'pay_1', 'source': 'subscription', 'source_id': out['id']}}).encode()
        got = self.bill.webhook(note, hmac.new(b'whsec', note, hashlib.sha256).hexdigest())
        self.assertEqual((got['used'], got['domain'], got['plan']), (True, 'kaali.in', 'swiss'))


class AddonSetsItselfUp(unittest.TestCase):
    """Paid → Dejoiy Mail sets the company up in Swiss Mail and keeps the key; ran out → Swiss Mail stops it; renewed → on again."""
    def test_life_of_an_addon(self):
        import relay, zimbra
        clock = Clock(); pay = FakePay(clock)
        bill = b.Billing(os.path.join(tempfile.mkdtemp(), 'b.sqlite'), pay, 'whsec', clock=clock)
        relays = relay.Relays(os.path.join(tempfile.mkdtemp(), 'r.json'), key=b'k' * 32, is_public=lambda h: True)
        relays.addon_until = bill.addon_until
        calls = []
        class Swiss:
            def setup(self, domain, name, limit): calls.append(('setup', domain, limit)); return {'api_key': 'djy_live_' + 'B' * 28}
            def update(self, domain, **change): calls.append(('update', domain, change))
            def get(self, domain, check=False): return {'domain': {'verification_status': 'pending'}}
        class Server: billing = bill; swiss = Swiss()
        Server.relays = relays
        me = type('H', (), {'server': Server})()
        sync = lambda: zimbra.Handler.sync_addon(me, 'kaali.in')
        sync(); self.assertEqual(calls, [])                                           # nothing bought: nothing set up
        out = bill.addon_checkout('kaali.in', 'a@kaali.in'); pay.charge(out['id'])
        sync(); sync()
        self.assertEqual(calls, [('setup', 'kaali.in', 10_000)])                      # once
        self.assertEqual(relays.config('kaali.in')['password'], 'djy_live_' + 'B' * 28)
        self.assertIsNone(relays.route('kaali.in', '', ['x@gmail.com']))              # DNS not checked yet: the usual way
        relays.set_addon('kaali.in', verified=True)
        bill.addon_cancel('kaali.in'); clock.t += 31 * DAY
        sync(); sync()
        self.assertEqual(calls[-1], ('update', 'kaali.in', {'status': 'suspended'})); self.assertEqual(len(calls), 2)
        out = bill.addon_checkout('kaali.in', 'a@kaali.in'); pay.charge(out['id'])
        sync()
        self.assertEqual(calls[-1], ('update', 'kaali.in', {'status': 'active'}))
        self.assertIsNotNone(relays.route('kaali.in', '', ['x@gmail.com']))
