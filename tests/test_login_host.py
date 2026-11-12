"""A company's own sign-in address: what names are allowed, and when it counts as pointing here."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

class LoginHostTests(unittest.TestCase):
    def test_only_a_subdomain_of_their_own_domain(self):
        ok = lambda h: z.clean_login_host(h, 'mail.dejoiy.com', 'acme.in')
        self.assertEqual(ok(' Mail.Acme.in. '), 'mail.acme.in')
        for bad in ('acme.in', 'mail.other.in', 'mail.dejoiy.com', 'x.dejoiy.com', 'evilacme.in', 'https://mail.acme.in', 'mail.acme.in/x', '10.0.0.1', 'mail..acme.in', '-a.acme.in', ''):
            with self.assertRaises(z.APIError, msg=bad): ok(bad)

    def test_points_here_by_cname_or_same_address(self):
        dns = {('mail.acme.in', 'CNAME'): ['mail.dejoiy.com'], ('a.acme.in', 'A'): ['1.2.3.4'], ('b.acme.in', 'A'): ['9.9.9.9'], ('mail.dejoiy.com', 'A'): ['1.2.3.4']}
        look = lambda name, kind: dns.get((name, kind), [])
        self.assertTrue(z.host_points_here('mail.acme.in', 'mail.dejoiy.com', look))
        self.assertTrue(z.host_points_here('a.acme.in', 'mail.dejoiy.com', look))
        self.assertFalse(z.host_points_here('b.acme.in', 'mail.dejoiy.com', look))
        self.assertFalse(z.host_points_here('none.acme.in', 'mail.dejoiy.com', look))

    def test_brand_is_plain_text_and_one_colour(self):
        b = z.clean_brand({'name': '<b>Acme</b>\n Mail', 'tagline': 'x' * 300, 'colour': '#1F5CE0'})
        self.assertEqual(b['name'], 'bAcme/b Mail'); self.assertEqual(len(b['tagline']), 120); self.assertEqual(b['colour'], '#1f5ce0')
        with self.assertRaises(z.APIError): z.clean_brand({'colour': 'red;background:url(x)'})

if __name__ == '__main__': unittest.main()


import json, threading, time, urllib.request, urllib.error
from unittest.mock import Mock

class LoginHostHTTPTests(unittest.TestCase):
    """On a company's own address: its page is branded, only its mailboxes sign in, and only its own origin is accepted."""
    @classmethod
    def setUpClass(cls):
        cls.server = z.ThreadingHTTPServer(('127.0.0.1', 0), z.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port); cls.server.app_origin = cls.url; cls.server.attempts = {}
        cls.server.zimbra = Mock(); cls.server.zimbra.login.return_value = ('t', 3600); cls.server.zimbra.capabilities.return_value = {}; cls.server.zimbra.account_id.return_value = 'id1'
        cls.server.hosts = z.AppearanceStore(None, 'hosts')
        cls.server.hosts.put('all', {'mail.acme.in': {'domain': 'acme.in', 'brand': {'name': 'Acme', 'tagline': '', 'colour': '#112233'}}})
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()
    def setUp(self): self.server.attempts = {}
    def call(self, path, data=None, host=None, origin=None):
        headers = {'Host': host} if host else {}
        if data is not None: headers.update({'Content-Type': 'application/json', 'Origin': origin})
        req = urllib.request.Request(self.url + path, None if data is None else json.dumps(data).encode(), headers)
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

    def test_brand_only_on_the_custom_address(self):
        self.assertEqual(self.call('/api/config', host='mail.acme.in')[1]['brand'], {'name': 'Acme', 'tagline': '', 'colour': '#112233', 'logo': '', 'domain': 'acme.in'})
        self.assertNotIn('brand', self.call('/api/config')[1])
        self.assertNotIn('brand', self.call('/api/config', host='mail.unknown.in')[1])

    def test_brand_follows_the_company_on_the_main_site_too(self):
        logo = 'a' * 32 + '.png'
        self.server.hosts.put('brands', {'acme.in': {'name': 'Acme', 'tagline': 'Hi', 'colour': '#112233', 'logo': logo}, 'evil.in': {'name': 'X', 'logo': '../../etc/passwd'}})
        def session_for(email):
            req = urllib.request.Request(self.url + '/api/login', json.dumps({'email': email, 'password': 'pw'}).encode(), {'Content-Type': 'application/json', 'Origin': self.url})
            with urllib.request.urlopen(req) as r: cookie = r.headers['Set-Cookie'].split(';')[0]
            with urllib.request.urlopen(urllib.request.Request(self.url + '/api/session', headers={'Cookie': cookie})) as r: return json.loads(r.read())
        try:
            self.assertEqual(session_for('priya@acme.in')['brand'], {'name': 'Acme', 'tagline': 'Hi', 'colour': '#112233', 'logo': self.url + '/media/' + logo, 'domain': 'acme.in'})
            self.assertNotIn('brand', session_for('someone@plain.in'))            # companies without a brand see Dejoiy Mail
            self.assertEqual(session_for('a@evil.in')['brand']['logo'], '')       # only a stored image name ever becomes a link
        finally: self.server.hosts.put('brands', {})

    def test_sign_in_rules(self):
        login = lambda email, host, origin: self.call('/api/login', {'email': email, 'password': 'pw'}, host, origin)
        self.assertEqual(login('priya@acme.in', 'mail.acme.in', 'https://mail.acme.in')[0], 200)
        self.assertEqual(login('priya', 'mail.acme.in', 'https://mail.acme.in')[0], 200)            # bare name = their domain
        self.assertEqual(self.server.zimbra.login.call_args[0][0], 'priya@acme.in')
        self.assertEqual(login('x@other.in', 'mail.acme.in', 'https://mail.acme.in')[0], 403)        # other companies: no
        self.assertEqual(login('priya@acme.in', 'mail.unknown.in', 'https://mail.unknown.in')[0], 403)  # unverified address: no
        self.assertEqual(login('priya@acme.in', None, 'https://mail.acme.in')[0], 403)               # custom origin on the main site: no
        self.assertEqual(login('priya@acme.in', 'mail.acme.in', 'https://evil.example')[0], 403)

    def test_sign_ins_are_logged_without_passwords(self):
        self.server.audit = z.AuditLog()
        self.call('/api/login', {'email': 'priya@acme.in', 'password': 'pw-secret'}, 'mail.acme.in', 'https://mail.acme.in')
        self.server.zimbra.login.side_effect = z.APIError('Wrong email or password', 401)
        self.call('/api/login', {'email': 'priya@acme.in', 'password': 'bad-secret'}, 'mail.acme.in', 'https://mail.acme.in')
        self.server.zimbra.login.side_effect = None
        rows = self.server.audit.db.execute('SELECT kind,actor,target,ip FROM events ORDER BY ts').fetchall()
        self.assertEqual([r[0] for r in rows], ['signin', 'signin_failed']); self.assertEqual(rows[0][1], 'priya@acme.in')
        self.assertNotIn('secret', json.dumps(rows))


class AuditLogTests(unittest.TestCase):
    def test_report_counts_and_scope(self):
        log = z.AuditLog(); now = 1_800_000_000.0
        log.add('send', 'a@acme.in', n=3, now=now); log.add('send', 'b@acme.in', n=1, now=now - 86400)
        log.add('signin', 'a@acme.in', ip='1.2.3.4', now=now)
        for _ in range(5): log.add('signin_failed', 'a@acme.in', ip='6.6.6.6', now=now)
        log.add('send', 'x@other.in', n=9, now=now); log.add('admin:password', 'boss@acme.in', 'a@acme.in', now=now)
        log.add('send', 'a@acme.in', n=50, now=now - 40 * 86400)   # older than the window
        r = log.report('acme.in', now=now)
        self.assertEqual(r['totals'], {'sent': 4, 'signins': 1, 'failed': 5, 'active': 2})
        self.assertEqual(len(r['days']), 14); self.assertEqual(r['days'][-1]['sent'], 3); self.assertEqual(r['days'][-2]['sent'], 1)
        self.assertEqual(r['topSenders'][0], {'email': 'a@acme.in', 'count': 3}); self.assertEqual(r['failedSignins'], [{'email': 'a@acme.in', 'count': 5}])
        self.assertEqual([e['kind'] for e in r['audit']], ['admin:password']); self.assertEqual(r['audit'][0]['target'], 'a@acme.in')
        self.assertNotIn('other.in', json.dumps(r))                 # a company admin never sees another company
        self.assertEqual(log.report(None, now=now)['totals']['sent'], 13)

    def test_old_events_are_dropped(self):
        log = z.AuditLog(); log.add('send', 'a@acme.in', now=1000.0); log.add('send', 'a@acme.in', now=1000.0 + 91 * 86400)
        self.assertEqual(log.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 1)


class ShineAdminTests(unittest.TestCase):
    """Chat & meetings in the admin console: a company admin can only reach its own company's Shine."""
    @classmethod
    def setUpClass(cls):
        cls.server = z.ThreadingHTTPServer(('127.0.0.1', 0), z.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port); cls.server.app_origin = cls.url; cls.server.attempts = {}
        cls.server.zimbra = Mock(); cls.server.zimbra.login.return_value = ('t', 3600); cls.server.zimbra.capabilities.return_value = {}; cls.server.zimbra.account_id.return_value = 'id1'
        cls.server.admin = Mock(); cls.server.admin.actor_perms.return_value = None
        cls.server.audit = z.AuditLog()
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()
    def setUp(self):
        self.server.attempts = {}; self.sent = []
        self.real = z.Handler.shine_admin_post
        z.Handler.shine_admin_post = lambda handler, payload: (self.sent.append(payload), {'ok': True})[1]
    def tearDown(self): z.Handler.shine_admin_post = self.real
    def admin(self, email, scope):
        req = urllib.request.Request(self.url + '/api/login', json.dumps({'email': email, 'password': 'pw'}).encode(), {'Content-Type': 'application/json', 'Origin': self.url})
        with urllib.request.urlopen(req) as r: cookie = r.headers['Set-Cookie'].split(';')[0]; csrf = json.loads(r.read())['csrf']
        z.SESSIONS[cookie.split('=')[1]].update(admin_token='a', admin_expires=time.time() + 600, admin_scope=scope)
        def act(data):
            req = urllib.request.Request(self.url + '/api/admin/action', json.dumps(data).encode(), {'Content-Type': 'application/json', 'Origin': self.url, 'Cookie': cookie, 'X-CSRF-Token': csrf})
            try:
                with urllib.request.urlopen(req) as r: return r.status
            except urllib.error.HTTPError as e: return e.code
        return act

    def test_company_admin_is_kept_to_its_own_company(self):
        act = self.admin('boss@acme.in', 'acme.in')
        self.assertEqual(act({'op': 'shine_summary'}), 200)
        self.assertEqual(self.sent[-1], {'op': 'summary', 'actor': 'boss@acme.in', 'scope': 'acme.in'})
        self.assertEqual(act({'op': 'shine_set_active', 'email': 'x@other.in', 'active': False}), 403)
        self.assertEqual(len(self.sent), 1)                                   # nothing was sent to Shine for the other company
        self.assertEqual(act({'op': 'shine_set_active', 'email': 'Priya@Acme.in', 'active': False}), 200)
        self.assertEqual(self.sent[-1], {'op': 'set_active', 'actor': 'boss@acme.in', 'scope': 'acme.in', 'email': 'priya@acme.in', 'active': False})
        kinds = [r[0] for r in self.server.audit.db.execute('SELECT kind FROM events').fetchall()]
        self.assertIn('admin:shine_set_active', kinds)

    def test_platform_admin_has_no_scope_and_needs_the_admin_step(self):
        act = self.admin('root@dejoiy.com', None)
        self.assertEqual(act({'op': 'shine_end_meeting', 'meetingId': 'm1'}), 200)
        self.assertEqual(self.sent[-1], {'op': 'end_meeting', 'actor': 'root@dejoiy.com', 'meetingId': 'm1'})
        plain = self.admin('user@acme.in', 'acme.in'); z.SESSIONS[next(k for k, v in z.SESSIONS.items() if v['user']['email'] == 'user@acme.in')].pop('admin_token')
        self.assertEqual(plain({'op': 'shine_summary'}), 403)                 # no admin sign-in: nothing
