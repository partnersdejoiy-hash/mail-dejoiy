"""Passkeys: the second step after the password. A fake authenticator (real P-256 and RSA keys from the
`cryptography` library, used here only) makes what a phone would; the server code checks it with its own maths."""
import hashlib, json, struct, sys, threading, unittest, uuid, time
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import passkeys as pk
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
except ImportError: ec = None

ORIGIN, RP = 'https://mail.dejoiy.com', 'dejoiy.com'

def enc(v):
    """CBOR, the few kinds an authenticator sends."""
    def head(major, n):
        if n < 24: return bytes([major << 5 | n])
        if n < 256: return bytes([major << 5 | 24, n])
        return bytes([major << 5 | 25]) + n.to_bytes(2, 'big')
    if isinstance(v, int): return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes): return head(2, len(v)) + v
    if isinstance(v, str): return head(3, len(v.encode())) + v.encode()
    if isinstance(v, dict): return head(5, len(v)) + b''.join(enc(k) + enc(x) for k, x in v.items())
    raise TypeError(v)

class Device:
    """One passkey on one phone."""
    def __init__(self, kind='ec', rp=RP, verified=True):
        self.kind, self.rp, self.flags, self.count = kind, rp, 1 | (4 if verified else 0), 0
        self.id = hashlib.sha256(str(id(self)).encode()).digest()
        self.key = ec.generate_private_key(ec.SECP256R1()) if kind == 'ec' else rsa.generate_private_key(65537, 2048)
    def cose(self):
        n = self.key.public_key().public_numbers()
        if self.kind == 'ec': return {1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, 'big'), -3: n.y.to_bytes(32, 'big')}
        return {1: 3, 3: -257, -1: n.n.to_bytes(256, 'big'), -2: n.e.to_bytes(3, 'big')}
    def auth(self, extra=b'', flags=0):
        self.count += 1
        return hashlib.sha256(self.rp.encode()).digest() + bytes([self.flags | flags]) + struct.pack('>I', self.count) + extra
    def make(self, options, origin=ORIGIN):
        client = json.dumps({'type': 'webauthn.create', 'challenge': options['challenge'], 'origin': origin}).encode()
        auth = self.auth(b'\0' * 16 + struct.pack('>H', len(self.id)) + self.id + enc(self.cose()), 64)
        return {'id': pk.b64(self.id), 'response': {'clientDataJSON': pk.b64(client), 'attestationObject': pk.b64(enc({'fmt': 'none', 'attStmt': {}, 'authData': auth}))}}
    def sign(self, options, origin=ORIGIN, kind='webauthn.get'):
        client = json.dumps({'type': kind, 'challenge': options['challenge'], 'origin': origin}).encode(); auth = self.auth()
        msg = auth + hashlib.sha256(client).digest()
        sig = self.key.sign(msg, ec.ECDSA(hashes.SHA256())) if self.kind == 'ec' else self.key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
        return {'id': pk.b64(self.id), 'response': {'clientDataJSON': pk.b64(client), 'authenticatorData': pk.b64(auth), 'signature': pk.b64(sig)}}

def ident(email): return str(uuid.uuid5(uuid.NAMESPACE_DNS, email.lower()))   # the mail server's id for a mailbox

class Store(dict):
    def get(self, k): return json.loads(json.dumps(dict.get(self, k, {})))   # what goes in must survive JSON, like the real store
    def put(self, k, v): self[k] = json.loads(json.dumps(v))

@unittest.skipIf(ec is None, 'the cryptography library is not installed')
class Core(unittest.TestCase):
    def setUp(self): self.clock = [1000.0]; self.keys = pk.Passkeys(Store(), now=lambda: self.clock[0]); self.me = 'a@acme.in'
    def enrol(self, device, **kw):
        options, state = self.keys.register_options(self.me, 'Asha', RP)
        return self.keys.register(self.me, state, device.make(options, **kw), ORIGIN, 'My phone')
    def signin(self, device, **kw):
        options, state = self.keys.login_options(self.me, RP)
        return self.keys.login(self.me, state, device.sign(options, **kw), ORIGIN)

    def test_register_then_sign_in_with_both_key_kinds(self):
        self.assertEqual(self.keys.login_options(self.me, RP), (None, None))          # no passkey: no second step
        for kind in ('ec', 'rsa'):
            d = Device(kind); out = self.enrol(d)
            self.assertTrue(self.signin(d)); self.assertTrue(self.signin(d))
        view = self.keys.view(self.me)
        self.assertEqual([k['name'] for k in view['passkeys']], ['My phone', 'My phone']); self.assertEqual(view['codesLeft'], 10)
        self.assertNotIn('codes', out)                                                 # codes come with the first passkey only
        self.assertNotIn('"key"', json.dumps(view))
    def test_refuses_what_is_not_this_persons_unlocked_device_on_this_site(self):
        d = Device(); self.enrol(d)
        cases = {'another site asked': dict(origin='https://evil.example'), 'a registration answer replayed': dict(kind='webauthn.create')}
        for why, kw in cases.items():
            with self.subTest(why), self.assertRaises(pk.PasskeyError): self.signin(d, **kw)
        with self.assertRaises(pk.PasskeyError): self.signin(Device())                 # somebody else's device
        options, state = self.keys.login_options(self.me, RP); answer = d.sign(options)
        other, state2 = self.keys.login_options(self.me, RP)
        with self.assertRaises(pk.PasskeyError): self.keys.login(self.me, state2, answer, ORIGIN)   # an old answer for a new challenge
        self.clock[0] += 301
        with self.assertRaises(pk.PasskeyError): self.keys.login(self.me, state, answer, ORIGIN)    # too late
        self.clock[0] = 1000; bad = d.sign(options); raw = bytearray(pk.unb64(bad['response']['signature'])); raw[-1] ^= 1
        bad['response']['signature'] = pk.b64(bytes(raw))
        with self.assertRaises(pk.PasskeyError): self.keys.login(self.me, state, bad, ORIGIN)       # a changed signature
        with self.assertRaises(pk.PasskeyError): self.enrol(Device(verified=False))                 # no fingerprint, face or PIN
        with self.assertRaises(pk.PasskeyError): self.enrol(Device(rp='evil.example'))
    def test_a_copied_passkey_is_refused(self):
        d = Device(); self.enrol(d); self.signin(d); self.signin(d)
        d.count = 1                                                                    # a clone that is behind the real one
        with self.assertRaises(pk.PasskeyError): self.signin(d)
    def test_recovery_codes_work_once(self):
        codes = self.enrol(Device())['codes']; self.assertEqual(len(set(codes)), 10)
        self.assertNotIn(codes[0], json.dumps(self.keys.store))                        # only their hashes are kept
        self.assertEqual(self.keys.use_code(self.me, codes[0].upper().replace('-', ' ')), 9)
        with self.assertRaises(pk.PasskeyError): self.keys.use_code(self.me, codes[0])
        with self.assertRaises(pk.PasskeyError): self.keys.use_code(self.me, 'aaaa-bbbb-cccc')
        fresh = self.keys.fresh_codes(self.me)['codes']
        with self.assertRaises(pk.PasskeyError): self.keys.use_code(self.me, codes[1])  # new codes retire the old
        self.assertEqual(self.keys.use_code(self.me, fresh[0]), 9)
    def test_remove_and_admin_reset_switch_the_step_off(self):
        d = Device(); codes = self.enrol(d)['codes']; short = self.keys.view(self.me)['passkeys'][0]['id']
        with self.assertRaises(pk.PasskeyError): self.enrol(d)                          # the same passkey twice
        self.assertFalse(self.keys.remove(self.me, short)['on']); self.assertFalse(self.keys.needed(self.me))
        with self.assertRaises(pk.PasskeyError): self.keys.use_code(self.me, codes[0])  # no passkey, no codes
        self.enrol(Device()); self.assertTrue(self.keys.reset(self.me)); self.assertFalse(self.keys.needed(self.me)); self.assertFalse(self.keys.reset(self.me))
    def test_another_site_gets_no_passkey_to_ask_for(self):
        self.enrol(Device()); options, _ = self.keys.login_options(self.me, 'mail.acme.in')
        self.assertEqual(options['allowCredentials'], [])                              # there a recovery code is the way in
    def test_rubbish_is_refused_not_crashed_on(self):
        options, state = self.keys.register_options(self.me, 'Asha', RP)
        for junk in (None, {}, {'response': {}}, {'response': {'clientDataJSON': '!!', 'attestationObject': 'AA'}},
                     {'response': {'clientDataJSON': pk.b64(json.dumps({'type': 'webauthn.create', 'challenge': options['challenge'], 'origin': ORIGIN}).encode()), 'attestationObject': pk.b64(b'\xbf\xff' * 40)}}):
            with self.subTest(junk=str(junk)[:40]), self.assertRaises(pk.PasskeyError): self.keys.register(self.me, state, junk, ORIGIN)

@unittest.skipIf(ec is None, 'the cryptography library is not installed')
class SignIn(unittest.TestCase):
    """Over HTTP: password, then the passkey, and only then a session."""
    @classmethod
    def setUpClass(cls):
        import zimbra as z; from test_accounts import Browser
        cls.z, cls.Browser = z, Browser
        cls.server = z.ThreadingHTTPServer(('127.0.0.1', 0), z.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port); cls.server.app_origin = cls.url
        zimbra = Mock(); zimbra.capabilities.return_value = {}; zimbra.account_id.side_effect = lambda token: ident(token.split('-', 1)[1])
        def login(email, password):
            if password != 'right': raise z.APIError('Wrong email or password', 401)
            return 'token-' + email, 3600
        zimbra.login.side_effect = login; cls.server.zimbra = zimbra
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()
    def setUp(self):
        self.server.attempts = {}; self.z.SESSIONS.clear(); self.z.PENDING.clear(); self.server.passkeys = pk.Passkeys(Store())
        self.b = self.Browser(self.url); self.assertEqual(self.b.call('/api/login', {'email': 'a@acme.in', 'password': 'right'})[0], 200); self.b.me()
        self.d = Device(rp='127.0.0.1')
        self.assertEqual(self.b.call('/api/passkeys', {'op': 'register_options', 'password': 'wrong'})[0], 403)   # adding one asks for the password
        options = self.b.call('/api/passkeys', {'op': 'register_options', 'password': 'right'})[1]['options']
        self.assertEqual(options['user']['name'], 'a@acme.in')
        status, out = self.b.call('/api/passkeys', {'op': 'register', 'credential': self.d.make(options, origin=self.url), 'name': 'Phone'})
        self.assertEqual(status, 200, out); self.codes = out['codes']
        self.b.call('/api/logout', {}); self.assertIsNone(self.b.me())
    def password(self, b=None, email='a@acme.in'):
        status, out = (b or self.b).call('/api/login', {'email': email, 'password': 'right'}); self.assertEqual(status, 200); return out

    def test_password_alone_no_longer_signs_in(self):
        out = self.password(); self.assertEqual(out['step'], 'passkey'); self.assertNotIn('user', out)
        self.assertIsNone(self.b.me()); self.assertEqual(len(self.z.SESSIONS), 0)
        self.assertEqual(self.password(email='A@Acme.in')['step'], 'passkey')            # however the address is typed
    def test_passkey_finishes_the_sign_in(self):
        out = self.password()
        status, done = self.b.call('/api/login/passkey', {'pending': out['pending'], 'assertion': self.d.sign(out['options'], origin=self.url)})
        self.assertEqual(status, 200, done); self.assertEqual(self.b.me(), 'a@acme.in')
        self.assertEqual(self.b.call('/api/login/passkey', {'pending': out['pending'], 'code': self.codes[0]})[0], 400)   # the step is used up
    def test_recovery_code_finishes_it_once(self):
        out = self.password(); self.assertEqual(self.b.call('/api/login/passkey', {'pending': out['pending'], 'code': self.codes[0]})[0], 200)
        self.assertEqual(self.b.me(), 'a@acme.in'); self.assertEqual(self.b.call('/api/passkeys', {'op': 'view'})[1]['codesLeft'], 9)
        other = self.Browser(self.url); out = self.password(other)
        self.assertEqual(other.call('/api/login/passkey', {'pending': out['pending'], 'code': self.codes[0]})[0], 400); self.assertIsNone(other.me())
    def test_five_wrong_tries_and_it_is_the_password_again(self):
        out = self.password()
        for _ in range(5): self.assertEqual(self.b.call('/api/login/passkey', {'pending': out['pending'], 'code': 'nope'})[0], 400)
        self.assertEqual(self.b.call('/api/login/passkey', {'pending': out['pending'], 'code': self.codes[0]})[0], 400)
        self.assertIsNone(self.b.me()); self.assertEqual(len(self.keys_left()), 10)
    def keys_left(self): return self.server.passkeys.data(ident('a@acme.in'))['codes']
    def test_adding_the_account_beside_another_asks_too(self):
        b = self.Browser(self.url); b.call('/api/login', {'email': 'b@acme.in', 'password': 'right'}); b.me()
        status, out = b.call('/api/accounts/add', {'email': 'a@acme.in', 'password': 'right'})
        self.assertEqual((status, out['step']), (200, 'passkey')); self.assertEqual(b.me(), 'b@acme.in')
        self.assertEqual([a['email'] for a in b.call('/api/accounts')[1]['accounts']], ['b@acme.in'])
        self.assertEqual(b.call('/api/login/passkey', {'pending': out['pending'], 'assertion': self.d.sign(out['options'], origin=self.url)})[0], 200)
        self.assertEqual(b.me(), 'a@acme.in'); self.assertEqual([a['email'] for a in b.call('/api/accounts')[1]['accounts']], ['a@acme.in', 'b@acme.in'])
    def test_removing_needs_the_password_and_switches_the_step_off(self):
        out = self.password(); self.b.call('/api/login/passkey', {'pending': out['pending'], 'code': self.codes[1]}); self.b.me()
        short = self.b.call('/api/passkeys', {'op': 'view'})[1]['passkeys'][0]['id']
        self.assertEqual(self.b.call('/api/passkeys', {'op': 'remove', 'id': short, 'password': 'wrong'})[0], 403)
        self.assertEqual(self.b.call('/api/passkeys', {'op': 'remove', 'id': short, 'password': 'right'})[1]['on'], False)
        self.b.call('/api/logout', {}); self.assertIn('user', self.password())

    def test_an_admin_removes_a_lost_passkey_in_their_own_company_only(self):
        z = self.z; boss = self.Browser(self.url); boss.call('/api/login', {'email': 'boss@acme.in', 'password': 'right'}); boss.me()
        sid = boss.jar['dejoiy_session']; z.SESSIONS[sid] = {**z.SESSIONS[sid], 'admin_token': 't', 'admin_expires': time.time() + 600, 'admin_scope': 'acme.in'}
        admin = Mock(); admin.actor_perms.return_value = None; self.server.admin = admin
        def found(email):
            out = ET.Element('r'); ET.SubElement(out, '{' + z.ADMIN + '}account', {'name': email}); admin.call.return_value = out
        try:
            found('x@other.in')
            self.assertEqual(boss.call('/api/admin/action', {'op': 'passkeys_reset', 'id': ident('a@acme.in')})[0], 403)
            self.assertEqual(self.password()['step'], 'passkey')                          # untouched
            found('a@acme.in')
            self.assertEqual(boss.call('/api/admin/action', {'op': 'passkeys_reset', 'id': ident('a@acme.in')})[1], {'ok': True, 'email': 'a@acme.in', 'had': True})
            self.server.attempts = {}; self.assertIn('user', self.password())            # the password alone signs in again
            self.assertEqual(boss.call('/api/admin/action', {'op': 'passkeys_reset', 'id': 'nope'})[0], 400)
        finally: del self.server.admin

class SharedSite(unittest.TestCase):
    def test_mail_and_admin_addresses_share_one_passkey_site(self):
        import zimbra as z
        def site(origin, app='https://mail.dejoiy.com', admin='https://admin-mail.dejoiy.com'):
            h = Mock(); h.headers = {'Origin': origin}; h.server.app_origin = app; h.server.admin_origin = admin
            return z.Handler.passkey_site(h)[0]
        self.assertEqual(site('https://mail.dejoiy.com'), 'dejoiy.com'); self.assertEqual(site('https://admin-mail.dejoiy.com'), 'dejoiy.com')
        self.assertEqual(site('https://mail.acme.in'), 'mail.acme.in')                  # a company's own address stands alone
        self.assertEqual(site('https://mail.dejoiy.com', admin=None), 'mail.dejoiy.com')
        self.assertEqual(site('https://a.in', app='https://a.in', admin='https://b.in'), 'a.in')   # never a bare "in"

if __name__ == '__main__': unittest.main()
