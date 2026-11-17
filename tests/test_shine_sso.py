import os, sys, unittest
from types import SimpleNamespace
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra


class ShineSsoTests(unittest.TestCase):
    """Continue with Dejoiy Mail: back to the Shine app, or to the meeting site with site=meet."""
    def handler(self, path, signed_in=True):
        h = zimbra.Handler.__new__(zimbra.Handler)
        h.path = path
        h.server = SimpleNamespace(shine_secret='s' * 32, shine_origin='https://app.shine.dejoiy.com', shine_meet_origin='https://meet.dejoiy.com')
        user = {'email': 'deepak@dejoiy.com', 'name': 'Deepak'}
        def session():
            if not signed_in: raise zimbra.APIError('Sign in', 401)
            return 'token', {'user': user}
        h.session = session
        h.shine_photo = lambda email: ''
        h.redirect = lambda url: url
        return h

    def test_app_by_default(self):
        url = self.handler('/shine/sso?return=%2Fapp%2Fchats').shine_sso()
        self.assertTrue(url.startswith('https://app.shine.dejoiy.com/auth/dejoiy#t='))
        self.assertTrue(url.endswith('&next=%2Fapp%2Fchats'))

    def test_meet_site(self):
        url = self.handler('/shine/sso?return=%2Fmeet%2Fteam%2FDJM-ABC-DEF&site=meet').shine_sso()
        self.assertTrue(url.startswith('https://meet.dejoiy.com/auth/dejoiy#t='))
        self.assertTrue(url.endswith('&next=%2Fmeet%2Fteam%2FDJM-ABC-DEF'))

    def test_signed_out_keeps_the_site_through_sign_in(self):
        url = self.handler('/shine/sso?return=%2Fmeet&site=meet', signed_in=False).shine_sso()
        self.assertEqual(url, '/?next=shine&site=meet&return=%2Fmeet')
        self.assertEqual(self.handler('/shine/sso?return=%2Fmeet', signed_in=False).shine_sso(), '/?next=shine&return=%2Fmeet')


if __name__ == '__main__': unittest.main()
