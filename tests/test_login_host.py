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


import json, threading, urllib.request, urllib.error
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
        self.assertEqual(self.call('/api/config', host='mail.acme.in')[1]['brand'], {'name': 'Acme', 'tagline': '', 'colour': '#112233', 'domain': 'acme.in'})
        self.assertNotIn('brand', self.call('/api/config')[1])
        self.assertNotIn('brand', self.call('/api/config', host='mail.unknown.in')[1])

    def test_sign_in_rules(self):
        login = lambda email, host, origin: self.call('/api/login', {'email': email, 'password': 'pw'}, host, origin)
        self.assertEqual(login('priya@acme.in', 'mail.acme.in', 'https://mail.acme.in')[0], 200)
        self.assertEqual(login('priya', 'mail.acme.in', 'https://mail.acme.in')[0], 200)            # bare name = their domain
        self.assertEqual(self.server.zimbra.login.call_args[0][0], 'priya@acme.in')
        self.assertEqual(login('x@other.in', 'mail.acme.in', 'https://mail.acme.in')[0], 403)        # other companies: no
        self.assertEqual(login('priya@acme.in', 'mail.unknown.in', 'https://mail.unknown.in')[0], 403)  # unverified address: no
        self.assertEqual(login('priya@acme.in', None, 'https://mail.acme.in')[0], 403)               # custom origin on the main site: no
        self.assertEqual(login('priya@acme.in', 'mail.acme.in', 'https://evil.example')[0], 403)
