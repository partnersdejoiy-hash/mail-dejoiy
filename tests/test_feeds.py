"""CSV feeds for live spreadsheets: numbers only, never content, and nothing runs as a formula."""
import csv, io, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import feeds, security, billing as b
import zimbra as z

DAY = 86400


class Feeds(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(); now = time.time()
        class S: pass
        s = self.s = S()
        s.audit = z.AuditLog(os.path.join(tmp, 'a.sqlite'))
        s.security = security.SecurityLog(os.path.join(tmp, 's.sqlite'))
        s.billing = b.Billing(os.path.join(tmp, 'b.sqlite'))
        s.avatars = z.AvatarStore(os.path.join(tmp, 'av.sqlite'))
        s.tickets = None; s.relays = None; s.reserved_domains = {'dejoiy.com'}
        s.live_sessions = lambda: 3
        s.audit.add('send', 'a@kaali.in', 'x@gmail.com', n=2, now=now - 3600)
        s.audit.add('send', '=cmd@evil.in', 'x', n=1, now=now - 3 * DAY)
        s.audit.add('signin', 'a@kaali.in', now=now - 60)
        s.audit.add('signin_failed', 'b@kaali.in', now=now - 60)
        s.security.record('a@kaali.in', '1', 'e@x.in', 'E', 'Secret subject', {'level': 'phishing', 'score': 9, 'reasons': ['x']})
        s.billing.db.execute('INSERT INTO subs VALUES (?,?,?,?,?)', ('kaali.in', 'team', 'month', now - 20 * DAY, now + 10 * DAY))
        s.billing.db.execute("INSERT INTO invoices (link_id, domain, plan, period, amount, mode, url, status, created, paid_at, paid_count) VALUES ('sub_1','kaali.in','team','month',35282,'live','u','active',?,?,2)", (now - 40 * DAY, now - 40 * DAY))
        s.billing.db.commit()

    def rows(self, text): return list(csv.reader(io.StringIO(text)))

    def test_mail_numbers_by_window(self):
        r = {row[0]: row[1:] for row in self.rows(feeds.mail(self.s, extra={'Mailboxes': 7})) if row}
        self.assertEqual(r['Mails sent from the web app'], ['2', '3', '3', '3'])
        self.assertEqual(r['Sign-ins'][0], '1'); self.assertEqual(r['Failed sign-ins'][0], '1')
        self.assertEqual(r['Phishing marked'][0], '1'); self.assertEqual(r['Mailboxes'], ['7']); self.assertEqual(r['Signed-in sessions'], ['3'])

    def test_admin_money_and_plans(self):
        r = {row[0]: row[1:] for row in self.rows(feeds.admin(self.s)) if row}
        self.assertEqual(r['Paying'], ['1']); self.assertEqual(r['On Team'], ['1'])
        self.assertEqual(r['Monthly recurring revenue, before GST'], ['299'])
        self.assertEqual(r['Collected, all time (with GST)'], ['705.64'])
        self.assertEqual(r['AutoPay subscriptions on'], ['1'])

    def test_daily_and_companies_carry_no_content(self):
        daily = self.rows(feeds.daily(self.s)); self.assertEqual(len(daily), 31)
        text = feeds.companies(self.s, mailboxes={'kaali.in': 4}) + feeds.daily(self.s) + feeds.mail(self.s) + feeds.admin(self.s)
        self.assertNotIn('Secret subject', text); self.assertNotIn('x@gmail.com', text)
        comp = {row[0]: row for row in self.rows(feeds.companies(self.s, mailboxes={'kaali.in': 4}))}
        self.assertEqual(comp['kaali.in'][1:3], ['paying', 'team']); self.assertEqual(comp['kaali.in'][5], '4')
        self.assertIn('evil.in', comp)

    def test_formulas_are_defused_and_token_is_kept(self):
        self.assertEqual(self.rows(feeds.to_csv(['a'], [['=HYPERLINK("x")'], [-5], ['+1']]))[1:], [["'=HYPERLINK(\"x\")"], ['-5'], ["'+1"]])
        tmp = tempfile.mkdtemp(); t = feeds.token(tmp)
        self.assertEqual(feeds.token(tmp), t); self.assertGreater(len(t), 20)
        self.assertEqual(oct(os.stat(os.path.join(tmp, 'feed-token')).st_mode & 0o777), '0o600')


if __name__ == '__main__': unittest.main()


class Status(unittest.TestCase):
    def test_up_slow_down_and_server_numbers(self):
        import io as _io, urllib.error
        class R(_io.BytesIO):
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): pass
        def opener(req, timeout):
            if 'down' in req.full_url: raise OSError('refused')
            if 'boom' in req.full_url: raise urllib.error.HTTPError(req.full_url, 502, 'x', {}, None)
            return R(b'ok')
        os.environ['STATUS_CHECKS'] = 'A|https://a.example/,B|https://down.example/,C|https://boom.example/'
        try: rows = list(csv.reader(io.StringIO(feeds.status(tempfile.mkdtemp(), True, opener=opener))))
        finally: del os.environ['STATUS_CHECKS']
        by = {r[0]: r for r in rows if r}
        self.assertEqual((by['A'][1], by['A'][3]), ('UP', '200'))
        self.assertEqual(by['B'][1], 'DOWN'); self.assertEqual((by['C'][1], by['C'][3]), ('DOWN', '502'))
        self.assertEqual(by['Services up'][1], '1 of 3')
        self.assertEqual(by['Mail system (Zimbra) answering'][1], 'UP')
        self.assertIn('Disk used', by)
