"""Subscriptions paid through Dejoiy Pay, against a fake Dejoiy Pay (no network)."""
import hashlib, hmac, io, json, os, sys, tempfile, unittest, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import billing as b

DAY = 86400


class FakePay:
    mode = 'test'
    def __init__(self): self.links = {}; self.made = []
    def create_link(self, **fields):
        self.made.append(fields); link_id = f'plink_{len(self.made)}'
        self.links[link_id] = 'created'
        return {'id': link_id, 'short_url': f'https://pay.dejoiy.com/pay/c{len(self.made)}', 'mode': 'test', 'status': 'created'}
    def link(self, link_id): return {'id': link_id, 'status': self.links[link_id]}


class Clock:
    def __init__(self): self.t = 1_800_000_000.0
    def __call__(self): return self.t


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.pay = FakePay()
        self.bill = b.Billing(os.path.join(tempfile.mkdtemp(), 'billing.sqlite'), self.pay, 'whsec', clock=self.clock)

    def test_prices_include_gst_and_match_the_home_page(self):
        self.assertEqual(b.price_paise('starter', 'month'), 11682)      # ₹99 + 18%
        self.assertEqual(b.price_paise('business', 'year'), 706820)     # ₹5,990 + 18%
        home = open(os.path.join(os.path.dirname(__file__), '..', 'web', 'js', 'signup.js')).read()
        for key, p in b.PLANS.items(): self.assertIn(f'{key}:["{p["name"]}",{p["month"]},{p["year"]}', home)

    def test_trial_then_paid_plan_keeps_trial_days(self):
        s = self.bill.status('kaali.in')
        self.assertEqual((s['state'], s['daysLeft']), ('trial', 11))
        out = self.bill.checkout('kaali.in', 'team', 'year', 'boss@kaali.in', 'Boss')
        self.assertEqual(self.pay.made[0]['amount'], b.price_paise('team', 'year'))
        self.assertEqual(self.pay.made[0]['notes']['domain'], 'kaali.in')
        self.assertTrue(out['url'].startswith('https://pay.dejoiy.com/'))
        self.assertEqual(self.bill.status('kaali.in')['open']['id'], out['id'])
        self.clock.t += 2 * DAY
        self.pay.links[out['id']] = 'paid'                 # paid on pay.dejoiy.com; the page asks
        s = self.bill.status('kaali.in')
        self.assertEqual((s['state'], s['plan'], s['period'], s['mailboxes']), ('active', 'team', 'year', 101))
        self.assertEqual(s['daysLeft'], 365 + 9)           # the 9 trial days left are kept
        self.assertIsNone(s['open'])

    def test_unpaid_link_buys_nothing_and_trial_runs_out(self):
        self.bill.checkout('kaali.in', 'starter', 'month', 'a@kaali.in')
        self.clock.t += 12 * DAY
        self.assertEqual(self.bill.status('kaali.in')['state'], 'expired')

    def test_paying_again_extends_and_twice_counts_once(self):
        first = self.bill.checkout('kaali.in', 'starter', 'month', 'a@kaali.in')
        self.assertTrue(self.bill.paid(first['id'])); self.assertFalse(self.bill.paid(first['id']))
        ends = self.bill.status('kaali.in')['ends']
        second = self.bill.checkout('kaali.in', 'starter', 'month', 'a@kaali.in')
        self.bill.paid(second['id'])
        self.assertEqual(self.bill.status('kaali.in')['ends'], ends + 30 * DAY)

    def test_part_payment_does_not_start_a_plan(self):
        link = self.bill.checkout('kaali.in', 'team', 'month', 'a@kaali.in')
        self.assertFalse(self.bill.paid(link['id'], amount=100))
        self.assertEqual(self.bill.status('kaali.in')['state'], 'trial')

    def test_webhook_needs_signature_and_a_paid_link(self):
        link = self.bill.checkout('kaali.in', 'team', 'month', 'a@kaali.in')
        note = json.dumps({'event': 'payment.captured', 'payload': {'id': 'pay_1', 'source': 'link', 'source_id': link['id'], 'amount': 35282}}).encode()
        sign = lambda raw, key='whsec': hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()
        with self.assertRaises(b.BillingError): self.bill.webhook(note, sign(note, 'wrong'))
        self.assertFalse(self.bill.webhook(note, sign(note))['used'])        # Dejoiy Pay says the link isn't paid yet
        self.pay.links[link['id']] = 'paid'
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
