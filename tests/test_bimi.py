"""Sender logos (BIMI): only for mail our own server verified, only safe SVGs, only from the public internet."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

class VerifiedSender(unittest.TestCase):
    def test_only_our_servers_dmarc_pass_for_that_domain(self):
        ours = 'mail.dejoiy.com; dkim=pass header.d=paypal.com; dmarc=pass (p=reject) header.from=paypal.com'
        self.assertEqual(z.verified_sender([ours], 'Service@PayPal.com', 'mail.dejoiy.com'), 'paypal.com')
        forged = 'mx.google.com; dmarc=pass header.from=paypal.com'                      # written by the sender, not by us
        self.assertEqual(z.verified_sender([forged], 'service@paypal.com', 'mail.dejoiy.com'), '')
        self.assertEqual(z.verified_sender(['mail.dejoiy.com; dmarc=fail header.from=paypal.com'], 'service@paypal.com', 'mail.dejoiy.com'), '')
        self.assertEqual(z.verified_sender(['mail.dejoiy.com; dmarc=pass header.from=evil.com'], 'service@paypal.com', 'mail.dejoiy.com'), '')
        self.assertEqual(z.verified_sender(['mail.dejoiy.com; spf=pass; notdmarc=pass'], 'a@b.com', 'mail.dejoiy.com'), '')
        self.assertEqual(z.verified_sender([], 'a@b.com', 'mail.dejoiy.com'), ''); self.assertEqual(z.verified_sender([ours], '', 'mail.dejoiy.com'), '')

class BimiRecord(unittest.TestCase):
    def dns(self, **records): return lambda name, kind='TXT': records.get(name.replace('.', '_').replace('-', '_'), [])
    def test_needs_an_enforced_dmarc_policy_and_an_https_logo(self):
        good = self.dns(_dmarc_shop_in=['v=DMARC1; p=reject'], default__bimi_shop_in=['v=BIMI1; l=https://shop.in/logo.svg; a='])
        self.assertEqual(z.bimi_record('shop.in', good), 'https://shop.in/logo.svg')
        watching = self.dns(_dmarc_shop_in=['v=DMARC1; p=none'], default__bimi_shop_in=['v=BIMI1; l=https://shop.in/logo.svg'])
        self.assertEqual(z.bimi_record('shop.in', watching), '')
        plain_http = self.dns(_dmarc_shop_in=['v=DMARC1; p=quarantine'], default__bimi_shop_in=['v=BIMI1; l=http://shop.in/logo.svg'])
        self.assertEqual(z.bimi_record('shop.in', plain_http), '')
        self.assertEqual(z.bimi_record('shop.in', self.dns(_dmarc_shop_in=['v=DMARC1; p=reject'])), '')

class LogoSafety(unittest.TestCase):
    def test_plain_pictures_only(self):
        self.assertTrue(z.clean_bimi_svg(open(os.path.join(os.path.dirname(__file__), '..', 'web', 'assets', 'brand', 'bimi-dejoiy.svg'), 'rb').read()))
        for bad in (b'<svg><script>alert(1)</script></svg>', b'<svg onload="x()"></svg>', b'<svg><a href="https://x">y</a></svg>', b'<svg><image href="https://x/y.png"/></svg>',
                    b'<svg><foreignObject><iframe src="x"/></foreignObject></svg>', b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg>&x;</svg>', b'<html></html>', b'', b'<svg>' + b'a' * 200000):
            self.assertFalse(z.clean_bimi_svg(bad), bad[:40])
    def test_never_fetches_from_inside_our_network(self):
        for url in ('http://shop.in/logo.svg', 'https://127.0.0.1/logo.svg', 'https://localhost/logo.svg', 'https://10.0.0.5/l.svg', 'https://169.254.169.254/latest', 'https://user:pw@shop.in/l.svg', 'https://shop.in:8443/l.svg'):
            self.assertIsNone(z.fetch_bimi_logo(url), url)

class DnsSetup(unittest.TestCase):
    def test_watch_only_dmarc_is_flagged_and_dejoiy_gets_a_bimi_record(self):
        answers = {('_dmarc.dejoiy.com', 'TXT'): ['v=DMARC1; p=none'], ('default._bimi.dejoiy.com', 'TXT'): []}
        real = z.dns_lookup; z.dns_lookup = lambda name, kind='TXT': answers.get((name, kind), [])
        try: records = {r['kind']: r for r in z.domain_records('dejoiy.com', 'mail.dejoiy.com', None, 'https://mail.dejoiy.com/assets/brand/bimi-dejoiy.svg')}
        finally: z.dns_lookup = real
        self.assertTrue(records['DMARC']['ok']); self.assertIn('p=none', records['DMARC']['note'])
        self.assertEqual(records['BIMI']['host'], 'default._bimi'); self.assertEqual(records['BIMI']['value'], 'v=BIMI1; l=https://mail.dejoiy.com/assets/brand/bimi-dejoiy.svg;')
        self.assertFalse(records['BIMI']['ok'])

if __name__ == '__main__': unittest.main()
