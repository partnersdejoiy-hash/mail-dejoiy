"""Several accounts in one browser: add one beside the open one, switch between them, and signing out opens the next."""
import json, sys, threading, unittest, urllib.error, urllib.request
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import zimbra as z

class Browser:
    """Keeps cookies and the request token like a browser tab does."""
    def __init__(self, url): self.url, self.jar, self.csrf = url, {}, ''
    def call(self, path, data=None):
        headers = {'Cookie': '; '.join(f'{k}={v}' for k, v in self.jar.items() if v)}
        if data is not None: headers.update({'Content-Type': 'application/json', 'Origin': self.url, 'X-CSRF-Token': self.csrf})
        req = urllib.request.Request(self.url + path, None if data is None else json.dumps(data).encode(), headers)
        try: r = urllib.request.urlopen(req); status = r.status
        except urllib.error.HTTPError as e: r = e; status = e.code
        for line in r.headers.get_all('Set-Cookie') or []:
            for k, m in SimpleCookie(line).items(): self.jar[k] = m.value
        return status, json.loads(r.read())
    def me(self):
        status, out = self.call('/api/session')
        if status == 200: self.csrf = out['csrf']
        return out.get('user', {}).get('email') if status == 200 else None

class Accounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = z.ThreadingHTTPServer(('127.0.0.1', 0), z.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port); cls.server.app_origin = cls.url
        zimbra = Mock(); zimbra.capabilities.return_value = {}; zimbra.account_id.side_effect = lambda token: token
        def login(email, password):
            if password != 'right': raise z.APIError('Wrong email or password', 401)
            return 'token-' + email, 3600
        zimbra.login.side_effect = login; cls.server.zimbra = zimbra
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()
    def setUp(self):
        self.server.attempts = {}; z.SESSIONS.clear()
        self.b = Browser(self.url); self.b.call('/api/login', {'email': 'a@acme.in', 'password': 'right'}); self.assertEqual(self.b.me(), 'a@acme.in')
    def add(self, email, password='right'):
        out = self.b.call('/api/accounts/add', {'email': email, 'password': password}); self.b.me(); return out
    def listed(self): return [(a['email'], a['current']) for a in self.b.call('/api/accounts')[1]['accounts']]

    def test_add_switch_and_sign_out(self):
        self.assertEqual(self.add('b@acme.in')[0], 200)
        self.assertEqual(self.b.me(), 'b@acme.in')                                            # the new one opens
        self.assertEqual(self.listed(), [('b@acme.in', True), ('a@acme.in', False)])
        self.assertEqual(self.b.call('/api/accounts/switch', {'email': 'a@acme.in'})[0], 200)
        self.assertEqual(self.b.me(), 'a@acme.in'); self.assertEqual(self.listed(), [('a@acme.in', True), ('b@acme.in', False)])
        self.assertEqual(self.b.call('/api/logout', {})[1], {'ok': True, 'next': 'b@acme.in'})   # signing out of one opens the next
        self.assertEqual(self.b.me(), 'b@acme.in'); self.assertEqual(self.listed(), [('b@acme.in', True)])
        self.assertEqual(self.b.call('/api/logout', {})[1], {'ok': True}); self.assertIsNone(self.b.me())
    def test_wrong_password_changes_nothing(self):
        self.assertEqual(self.add('b@acme.in', 'wrong')[0], 401)
        self.assertEqual(self.b.me(), 'a@acme.in'); self.assertEqual(self.listed(), [('a@acme.in', True)])
    def test_same_account_twice_and_the_limit(self):
        self.assertEqual(self.add('a@acme.in')[0], 400)
        for i in range(z.MAX_OTHER_ACCOUNTS): self.server.attempts = {}; self.assertEqual(self.add(f'u{i}@acme.in')[0], 200)
        self.server.attempts = {}; self.assertEqual(self.add('one-too-many@acme.in')[0], 400)
        self.server.attempts = {}; self.assertEqual(self.add('u0@acme.in')[0], 200)             # signing in a waiting one again is fine
        self.assertEqual(len(self.listed()), z.MAX_OTHER_ACCOUNTS + 1); self.assertEqual(len(z.SESSIONS), z.MAX_OTHER_ACCOUNTS + 1)
    def test_only_accounts_signed_in_on_this_browser(self):
        other = Browser(self.url); other.call('/api/login', {'email': 'x@other.in', 'password': 'right'}); other.me()
        self.assertEqual(self.b.call('/api/accounts/switch', {'email': 'x@other.in'})[0], 404)
        self.b.jar['dejoiy_others'] = 'not-a-real-session-id-aaaaaaaaaaaaaaaa'                  # a made-up id opens nothing
        self.assertEqual(self.listed(), [('a@acme.in', True)])
    def test_adding_needs_the_request_token(self):
        self.b.csrf = 'wrong'; self.assertEqual(self.b.call('/api/accounts/add', {'email': 'b@acme.in', 'password': 'right'})[0], 403)

if __name__ == '__main__': unittest.main()


class StaySignedIn(unittest.TestCase):
    """A sign-in lasts as long as the mail server's token (the company's policy), not one hour; never more than 30 days."""
    def lifetime(self, ms):
        client = z.Zimbra.__new__(z.Zimbra)
        client.call = lambda r, *a, **k: z.ET.fromstring(f'<AuthResponse xmlns="urn:zimbraAccount"><authToken>tok</authToken><lifetime>{ms}</lifetime></AuthResponse>')
        return client.login('a@acme.in', 'pw')[1]
    def test_policy_decides(self):
        self.assertEqual(self.lifetime(48 * 3600 * 1000), 48 * 3600)
        self.assertEqual(self.lifetime(3600 * 1000), 3600)
        self.assertEqual(self.lifetime(400 * 86400 * 1000), z.MAX_SESSION_SECONDS)


class MailboxName(unittest.TestCase):
    def test_a_new_person_is_known_by_the_name_on_their_mailbox(self):
        import xml.etree.ElementTree as ET
        client = z.Zimbra('https://mail.example'); out = ET.Element('r')
        for n, v in (('displayName', ' Deepanshu Chander Yaduvanshi '), ('zimbraIsAdminAccount', 'FALSE')):
            ET.SubElement(out, '{' + z.ACCOUNT + '}attr', {'name': n}).text = v
        client.call = lambda request, token=None: out
        self.assertEqual(client.capabilities('t'), {'isAdmin': False, 'canManageRoles': False, 'name': 'Deepanshu Chander Yaduvanshi'})
        out.remove(out[0]); self.assertNotIn('name', client.capabilities('t'))   # none given: the page keeps its own fallback
