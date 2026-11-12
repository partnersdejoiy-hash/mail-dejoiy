import time, unittest, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'server'))
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

if __name__ == '__main__':
    unittest.main()
