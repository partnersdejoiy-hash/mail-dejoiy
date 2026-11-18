"""Declaring a domain Dejoiy's own works even on a server without billing."""
import os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra

class Admin:
    def actor_perms(self, token, email, scope): return None
    def call(self, r, token=None): return None

class OwnDomainWithoutBilling(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.h = zimbra.Handler.__new__(zimbra.Handler)
        self.h.server = SimpleNamespace(billing=None, admin=Admin(), fixed_domains={'dejoiy.com'}, reserved_domains={'dejoiy.com'},
                                        own_file=str(d / 'own.json'), ses_file=None, promoted_file=None)
        self.h.admin_session = lambda s: (self.h.server.admin, 'tok', '')
        self.h.log = lambda *a, **k: None
        self.s = {'user': {'email': 'deepak.sharma@dejoiy.com'}}

    def test_declare_and_undo(self):
        h, s = self.h, self.s
        self.assertEqual(h.billing_action(s, {'op': 'billing_get', 'domain': 'anupurana-angan.co.in'})['state'], 'none')
        out = h.billing_action(s, {'op': 'billing_own', 'domain': 'anupurana-angan.co.in', 'on': True})
        self.assertEqual(out['state'], 'internal'); self.assertIn('anupurana-angan.co.in', h.server.reserved_domains)
        self.assertEqual(h.billing_action(s, {'op': 'billing_own', 'domain': 'anupurana-angan.co.in', 'on': False})['state'], 'none')
        with self.assertRaises(zimbra.APIError): h.billing_action(s, {'op': 'billing_checkout', 'domain': 'anupurana-angan.co.in'})

if __name__ == '__main__': unittest.main()
