"""Spam and phishing marks, the admins' list, and outside senders' photos."""
import io, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import security as sec

OK_AUTH = {'spf': 'pass', 'dkim': 'pass', 'dmarc': 'pass'}


class Marks(unittest.TestCase):
    def r(self, **kw):
        base = dict(sender='news@shop.example', name='Shop', subject='Your order', text_body='Thanks for your order.', auth=OK_AUTH, verified=True,
                    own_domains=('dejoiy.com',), recipient='ravi@kaali.in')
        base.update(kw); return sec.risk(**base)

    def test_ordinary_mail_gets_no_mark(self):
        self.assertIsNone(self.r()['level'])
        self.assertIsNone(self.r(html_body='<a href="https://shop.example/o/1">shop.example/o/1</a>')['level'])
        self.assertIsNone(self.r(html_body='<a href="https://click.mailer.example/t/1">shop.example</a>')['level'])   # verified newsletter tracking
        self.assertIsNone(self.r(sender='friend@gmail.com', name='Asha', verified=True)['level'])

    def test_bank_name_from_free_mail_with_a_lure_is_phishing(self):
        out = self.r(sender='alerts.sbi@gmail.com', name='SBI Alerts', verified=False, auth={'spf': 'pass', 'dmarc': 'pass'},
                     subject='KYC update pending', text_body='Your account will be blocked. Click here to login and update your KYC within 24 hours.')
        self.assertEqual(out['level'], 'phishing')
        self.assertTrue(any('Sbi' in r for r in out['reasons']))

    def test_lookalike_of_the_readers_own_company(self):
        out = self.r(sender='ceo@kaa1i.in', name='CEO', verified=False, auth={})
        self.assertEqual(out['level'], 'phishing'); self.assertIn('looks like your own kaali.in', out['reasons'][0])
        self.assertIsNone(self.r(sender='ceo@dejoiy.co.in', recipient='x@other.in', own_domains=())['level'])

    def test_failing_our_own_checks_while_claiming_our_domain(self):
        out = self.r(sender='payroll@kaali.in', name='Payroll', verified=False, auth={'spf': 'fail', 'dmarc': 'fail'})
        self.assertEqual(out['level'], 'phishing')

    def test_links_that_lie_and_tricky_attachments(self):
        self.assertEqual(self.r(verified=False, html_body='<a href="https://evil.example/x">www.hdfcbank.com</a>')['level'], 'phishing')
        self.assertEqual(self.r(attachments=['invoice.pdf.exe'])['level'], 'phishing')
        self.assertEqual(self.r(verified=False, html_body='<a href="https://user@evil.example">x</a><a href="http://203.0.113.9/login">y</a>')['level'], 'phishing')

    def test_spam_filter_and_score(self):
        self.assertEqual(self.r(spam_flag='YES')['level'], 'suspicious')
        self.assertEqual(self.r(spam_score='6.1')['level'], 'suspicious')
        self.assertIsNone(self.r(spam_score='1.0')['level'])

    def test_only_our_servers_stamp_counts(self):
        stamped = ['mail.dejoiy.com; spf=fail smtp.mailfrom=x.in; dmarc=fail header.from=x.in', 'evil.example; dmarc=pass']
        self.assertEqual(sec.auth_results(stamped, 'mail.dejoiy.com'), {'spf': 'fail', 'dmarc': 'fail'})
        self.assertEqual(sec.auth_results(['evil.example; dmarc=pass'], 'mail.dejoiy.com'), {})


class Log(unittest.TestCase):
    def test_company_admins_see_only_their_domain(self):
        log = sec.SecurityLog(os.path.join(tempfile.mkdtemp(), 's.sqlite'))
        v = {'level': 'phishing', 'score': 9, 'reasons': ['x']}
        self.assertTrue(log.record('a@kaali.in', '1', 'e@x.in', 'E', 'Hi', v))
        log.record('a@kaali.in', '1', 'e@x.in', 'E', 'Hi', v)                 # the same mail twice is one row
        log.record('b@other.in', '2', 'e@x.in', 'E', 'Hi', {'level': 'suspicious', 'score': 3, 'reasons': []})
        self.assertFalse(log.record('b@other.in', '3', 'e@x.in', 'E', 'Hi', {'level': None, 'score': 0, 'reasons': []}))
        self.assertEqual(len(log.list()['items']), 2)
        mine = log.list(['kaali.in'])
        self.assertEqual([x['mailbox'] for x in mine['items']], ['a@kaali.in']); self.assertEqual(mine['counts'], {'phishing': 1})
        self.assertEqual(len(log.list(level='suspicious')['items']), 1)
        self.assertEqual(log.list([])['items'], [])

    def test_scanner_logs_new_mail(self):
        log = sec.SecurityLog()
        scan = sec.SecurityScanner(log, lambda: ['kaali.in'], lambda box, mid: {'from': 'x@y.in', 'name': 'X', 'subject': 'S', 'risk': {'level': 'phishing', 'score': 7, 'reasons': ['r']}})
        self.assertEqual(scan.domains(), {'kaali.in'})
        scan.new_mail('kaali.in', 'a@kaali.in', {'id': '9', 'date': 1_800_000_000_000})
        self.assertEqual(log.list(days=90)['items'][0]['id'], '9')


class SenderPhotos(unittest.TestCase):
    def test_only_real_pictures_come_back(self):
        import zimbra
        png = b'\x89PNG\r\n\x1a\n' + b'0' * 50
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): pass
        seen = {}
        def opener(req, timeout): seen['url'] = req.full_url; return R(png)
        kind, raw = zimbra.fetch_gravatar(' Asha@Gmail.com ', opener=opener)
        self.assertEqual(kind, 'image/png')
        import hashlib
        self.assertIn(hashlib.sha256(b'asha@gmail.com').hexdigest(), seen['url']); self.assertIn('r=g', seen['url']); self.assertIn('d=404', seen['url'])
        self.assertIsNone(zimbra.fetch_gravatar('a@b.in', opener=lambda req, timeout: R(b'<svg onload=alert(1)>')))
        self.assertIsNone(zimbra.fetch_gravatar('a@b.in', opener=lambda req, timeout: R(png + b'0' * 300_000)))
        def nope(req, timeout): raise OSError('404')
        self.assertIsNone(zimbra.fetch_gravatar('a@b.in', opener=nope))


if __name__ == '__main__': unittest.main()
