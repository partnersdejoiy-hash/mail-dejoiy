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
