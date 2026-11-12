import time, unittest, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'server'))
import types, tempfile, os, stat
import zimbra as z
from zimbra import joi_signed, joi_read

class JoiLink(unittest.TestCase):
    def test_round_trip_and_rules(self):
        exp = int((time.time() + 60) * 1000)
        t = joi_signed('s3cret', {'app': 'mail', 'k': 'mailbox', 'e': 'a@b.com', 'exp': exp})
        self.assertEqual(joi_read('s3cret', t, 'mailbox', 120)['e'], 'a@b.com')
        self.assertIsNone(joi_read('other', t, 'mailbox', 120))        # wrong secret
        self.assertIsNone(joi_read('s3cret', t, 'login', 120))         # wrong kind
        self.assertIsNone(joi_read('s3cret', t, 'mailbox', 10))        # lives too long
        old = joi_signed('s3cret', {'app': 'mail', 'k': 'mailbox', 'e': 'a@b.com', 'exp': exp - 120000})
        self.assertIsNone(joi_read('s3cret', old, 'mailbox', 120))     # expired
        self.assertIsNone(joi_read('', t, 'mailbox', 120))

def mailbox_handler(sessions, grant_key='server-only', secret='shared'):
    """Handler.joi_mailbox with a stand-in server; returns (call, mailboxes read)."""
    read = []
    zim = types.SimpleNamespace(messages=lambda token: read.append(token) or {'emails': [{'folder': 'inbox', 'subject': 'hi', 'body': 'x', 'read': False}]})
    h = types.SimpleNamespace(server=types.SimpleNamespace(joi_secret=secret, joi_grant_key=grant_key, zimbra=zim), delegated=lambda e: 'tok:'+e)
    old = z.SESSIONS
    def call(data):
        z.SESSIONS = sessions
        try: return z.Handler.joi_mailbox(h, data)
        finally: z.SESSIONS = old
    return call, read

class JoiMailboxGrant(unittest.TestCase):
    def setUp(self):
        self.exp = int((time.time() + 60) * 1000)
        self.sessions = {'sid1': {'user': {'email': 'ravi@kaali.in'}, 'expires': time.time() + 3600, 'joi_grant': 'G1'}}
    def req(self, email, grant_email='ravi@kaali.in', g='G1', key='server-only', secret='shared'):
        return {'token': joi_signed(secret, {'app': 'mail', 'k': 'mailbox', 'e': email, 'exp': self.exp}),
                'grant': joi_signed(key, {'app': 'mail', 'k': 'grant', 'e': grant_email, 'g': g, 'exp': self.exp})}

    def test_owner_with_live_grant_reads_own_mailbox(self):
        call, read = mailbox_handler(self.sessions)
        out = call(self.req('ravi@kaali.in'))
        self.assertEqual(out['unread'], 1); self.assertEqual(read, ['tok:ravi@kaali.in'])

    def test_no_grant_or_grant_made_with_shared_secret_is_refused(self):
        call, read = mailbox_handler(self.sessions)
        bare = self.req('ravi@kaali.in'); bare.pop('grant')
        for data in (bare, self.req('ravi@kaali.in', key='shared')):  # Joi holds the shared secret, not the grant key
            with self.assertRaises(z.APIError): call(data)
        self.assertEqual(read, [])

    def test_cannot_read_someone_else(self):
        call, read = mailbox_handler(self.sessions)
        with self.assertRaises(z.APIError): call(self.req('boss@kaali.in'))  # grant is ravi's
        with self.assertRaises(z.APIError): call(self.req('boss@kaali.in', grant_email='boss@kaali.in'))  # the session is ravi's
        self.assertEqual(read, [])

    def test_grant_ends_with_sign_out_or_expiry(self):
        call, _ = mailbox_handler({})
        with self.assertRaises(z.APIError): call(self.req('ravi@kaali.in'))
        call, _ = mailbox_handler({'sid1': {**self.sessions['sid1'], 'expires': time.time() - 1}})
        with self.assertRaises(z.APIError): call(self.req('ravi@kaali.in'))

    def test_grant_key_file_is_private_and_stable(self):
        with tempfile.TemporaryDirectory() as d:
            k = z.joi_grant_key(d)
            self.assertEqual(k, z.joi_grant_key(d))
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, 'joi-grant.key')).st_mode), 0o600)

if __name__ == '__main__':
    unittest.main()
