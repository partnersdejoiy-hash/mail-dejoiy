"""Sign-in tokens Dejoiy Mail hands to Shine."""
import base64, hashlib, hmac, json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

def parts(token):
    body, sig = token.split('.')
    pad = lambda s: s + '=' * (-len(s) % 4)
    return body, sig, json.loads(base64.urlsafe_b64decode(pad(body)))

class ShineTokenTests(unittest.TestCase):
    def test_signed_with_shared_secret_and_expires(self):
        body, sig, claims = parts(z.shine_token('s3cret', 'Deepak@Dejoiy.com', 'Deepak', now=1000, ttl=120))
        good = base64.urlsafe_b64encode(hmac.new(b's3cret', body.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
        self.assertEqual(sig, good)
        self.assertEqual(claims['e'], 'deepak@dejoiy.com'); self.assertEqual(claims['x'], 1120000)
        self.assertNotIn('=', body + sig)

    def test_each_token_is_different(self):
        self.assertNotEqual(z.shine_token('k', 'a@b.in', ''), z.shine_token('k', 'a@b.in', ''))

    def test_return_path_stays_on_shine(self):
        for bad in ('https://evil.example', '//evil.example', '', 'javascript:alert(1)', '/a b'):
            self.assertEqual(z.safe_return(bad), '/app/chats')
        self.assertEqual(z.safe_return('/app/chats/c1?embed=1'), '/app/chats/c1?embed=1')

if __name__ == '__main__': unittest.main()
