"""Mailbox policies a company sets for itself: validation, what reaches the mail server, and who gets which policy."""
import os, sys, json, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

A = z.ADMIN
def account(ident, email, notes=''):
    return f'<account id="{ident}" name="{email}"><a n="zimbraNotes">{notes}</a></account>'
ID1, ID2 = '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222'

class FakeAdmin(z.ZimbraAdmin if hasattr(z, 'ZimbraAdmin') else object):
    pass

class PolicyRules(unittest.TestCase):
    def test_ranges_and_floor(self):
        ok = z.clean_policy({'name': 'Strict', 'rules': {'passwordMinLength': 14, 'lockoutAfter': 5, 'forwarding': False}})
        self.assertEqual(ok['rules']['passwordMinLength'], 14); self.assertEqual(ok['rules']['sessionHours'], 48)   # missing rules take the standard value
        for bad in ({'passwordMinLength': 6}, {'lockoutAfter': 2}, {'sessionHours': 0}, {'forwarding': 'no'}, {'trashDays': True}):
            with self.assertRaises(z.APIError, msg=bad): z.clean_policy({'name': 'x', 'rules': bad})
        with self.assertRaises(z.APIError): z.clean_policy({'name': '', 'rules': {}})

    def test_becomes_mail_server_settings(self):
        attrs = dict(z.policy_attrs(z.clean_policy({'name': 'Strict', 'rules': {'passwordMinLength': 14, 'passwordMaxAgeDays': 90, 'lockoutAfter': 5, 'lockoutMinutes': 15, 'forwarding': False, 'imap': False}})))
        self.assertEqual(attrs['zimbraPasswordMinLength'], '14'); self.assertEqual(attrs['zimbraPasswordMaxAge'], '90')
        self.assertEqual((attrs['zimbraPasswordLockoutEnabled'], attrs['zimbraPasswordLockoutMaxFailures'], attrs['zimbraPasswordLockoutDuration']), ('TRUE', '5', '15m'))
        self.assertEqual((attrs['zimbraFeatureMailForwardingEnabled'], attrs['zimbraImapEnabled']), ('FALSE', 'FALSE'))
        self.assertEqual(attrs['zimbraPrefMailForwardingAddress'], '')          # forwarding off also clears a forward already set
        self.assertEqual(attrs['zimbraNotes'], 'dejoiyPolicy:Strict')
        off = dict(z.policy_attrs(z.clean_policy({'name': 'Open', 'rules': {'lockoutAfter': 0}})))
        self.assertEqual(off['zimbraPasswordLockoutEnabled'], 'FALSE'); self.assertNotIn('zimbraPrefMailForwardingAddress', off)

    def test_saved_with_roles_and_survives_a_round_trip(self):
        notes = z.write_org('', policies=[z.clean_policy({'name': 'Strict', 'rules': {'passwordMinLength': 12}})], defaultPolicy='Strict')
        org = z.read_org(notes)
        self.assertEqual([p['name'] for p in org['policies']], ['Strict']); self.assertEqual(org['defaultPolicy'], 'Strict'); self.assertTrue(org['roles'])
        self.assertEqual(z.read_org('')['policies'][0]['name'], 'Standard')     # a company with nothing saved has the standard policy
        self.assertEqual(z.read_org(json.dumps({'mailPolicies': [{'name': 'Bad', 'rules': {'passwordMinLength': 2}}]}))['policies'][0]['name'], 'Standard')

class PolicyActions(unittest.TestCase):
    """Runs the admin operations against a fake mail server and checks exactly what it was asked to change."""
    def setUp(self):
        self.sent = []; self.notes = ''
        admin = object.__new__(next(c for c in vars(z).values() if isinstance(c, type) and hasattr(c, 'action') and hasattr(c, 'overview')))
        def call(request, token):
            tag = request.tag.split('}')[1]; self.sent.append((tag, request, token))
            if tag == 'GetDomainRequest': return z.ET.fromstring(f'<r xmlns="{A}"><domain id="d1" name="acme.in"><a n="zimbraNotes">{z.html.escape(self.notes)}</a></domain></r>')
            if tag == 'GetAllAccountsRequest': return z.ET.fromstring(f'<r xmlns="{A}">{account(ID1, "a@acme.in", "dejoiyPolicy:Strict")}{account(ID2, "b@acme.in")}</r>')
            if tag == 'GetAccountRequest': return z.ET.fromstring(f'<r xmlns="{A}">{account(ID2, "b@acme.in")}</r>')
            if tag == 'ModifyDomainRequest': self.notes = next(a.text for a in request.findall('{' + A + '}a') if a.get('n') == 'zimbraNotes')
            return z.ET.fromstring(f'<r xmlns="{A}"/>')
        admin.call = call; self.admin = admin
    def changes(self):
        return {r.find('{' + A + '}id').text: {a.get('n'): a.text for a in r.findall('{' + A + '}a')} for tag, r, _ in self.sent if tag == 'ModifyAccountRequest'}
    def act(self, data, scope='acme.in'):
        return self.admin.action('tok', data, 'boss@acme.in', scope, lambda: 'elevated', None)

    def test_save_applies_each_mailbox_its_own_or_the_default(self):
        policies = [{'name': 'Standard', 'rules': {}}, {'name': 'Strict', 'rules': {'passwordMinLength': 16, 'forwarding': False}}]
        out = self.act({'op': 'policies_save', 'domain': 'acme.in', 'policies': policies, 'default': 'Standard'})
        self.assertEqual((out['applied'], out['failed']), (2, 0))
        c = self.changes()
        self.assertEqual(c[ID1]['zimbraPasswordMinLength'], '16'); self.assertEqual(c[ID1]['zimbraFeatureMailForwardingEnabled'], 'FALSE')   # was on Strict: stays Strict
        self.assertEqual(c[ID2]['zimbraNotes'], 'dejoiyPolicy:Standard'); self.assertEqual(c[ID2]['zimbraPasswordMinLength'], '10')          # had none: gets the default
        self.assertEqual(self.act({'op': 'policies_get', 'domain': 'acme.in'})['default'], 'Standard')
        self.assertTrue(all(t == 'elevated' for tag, _, t in self.sent if tag.startswith('Modify')))

    def test_only_your_own_company_and_only_valid_policies(self):
        with self.assertRaises(z.APIError): self.act({'op': 'policies_save', 'domain': 'other.in', 'policies': [{'name': 'x', 'rules': {}}], 'default': 'x'})
        with self.assertRaises(z.APIError): self.act({'op': 'policies_save', 'domain': 'acme.in', 'policies': [{'name': 'x', 'rules': {'passwordMinLength': 4}}], 'default': 'x'})
        with self.assertRaises(z.APIError): self.act({'op': 'policies_save', 'domain': 'acme.in', 'policies': [{'name': 'x', 'rules': {}}, {'name': 'X', 'rules': {}}], 'default': 'x'})
        self.assertEqual(self.changes(), {})                                     # nothing was changed on any mailbox

    def test_assign_one_mailbox(self):
        self.notes = z.write_org('', policies=[z.standard_policy(), z.clean_policy({'name': 'Interns', 'rules': {'imap': False, 'sessionHours': 8}})], defaultPolicy='Standard')
        self.assertEqual(self.act({'op': 'policy_assign', 'id': ID2, 'policy': 'Interns'})['policy'], 'Interns')
        self.assertEqual(self.changes()[ID2]['zimbraAuthTokenLifetime'], '8h'); self.assertEqual(self.changes()[ID2]['zimbraImapEnabled'], 'FALSE')
        with self.assertRaises(z.APIError): self.act({'op': 'policy_assign', 'id': ID2, 'policy': 'Gone'})

if __name__ == '__main__': unittest.main()
