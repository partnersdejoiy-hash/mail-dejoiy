"""Departments and roles in the admin console, against a fake mail server."""
import json, os, sys, unittest
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

A = '{'+z.ADMIN+'}'
USER, SALES = 'a'*36, '0'*36

class Fake(z.Admin):
    def __init__(self):
        super().__init__('https://example.com'); self.calls = []
    def call(self, r, token=None):
        tag = r.tag.split('}')[1]; self.calls.append((tag, ET.tostring(r).decode(), token))
        out = ET.Element(A+tag.replace('Request', 'Response'))
        if tag == 'GetAccountRequest': ET.SubElement(out, A+'account', {'id': USER, 'name': 'ravi@kaali.in'})
        if tag == 'GetAllDistributionListsRequest':
            for ident, name, mark in ((SALES, 'Sales', z.DEPARTMENT_MARK), ('1'*36, 'team', None)):
                d = ET.SubElement(out, A+'dl', {'id': ident, 'name': name.lower()+'@kaali.in'})
                ET.SubElement(d, A+'a', {'n': 'displayName'}).text = name
                if mark: ET.SubElement(d, A+'a', {'n': 'zimbraNotes'}).text = mark
        if tag == 'GetDomainRequest': ET.SubElement(out, A+'domain', {'id': 'd'*36, 'name': 'kaali.in'})
        return out

class OrgTests(unittest.TestCase):
    def test_department_is_marked_team_list(self):
        a = Fake(); a.action('t', {'op': 'create_department', 'name': 'Sales', 'email': 'sales@kaali.in'}, 'boss@kaali.in', 'kaali.in')
        self.assertIn(z.DEPARTMENT_MARK, a.calls[-1][1])

    def test_set_department_joins_list_and_sets_ou(self):
        a = Fake(); a.action('t', {'op': 'set_department', 'id': USER, 'department': SALES}, 'boss@kaali.in', 'kaali.in')
        tags = [c[0] for c in a.calls]
        self.assertIn('AddDistributionListMemberRequest', tags)
        self.assertNotIn('RemoveDistributionListMemberRequest', tags)  # the plain team list is not a department
        self.assertIn('<ns0:a n="ou">Sales</ns0:a>', a.calls[-1][1])

    def test_roles_saved_on_domain_with_elevated_token(self):
        a = Fake()
        out = a.action('t', {'op': 'save_roles', 'domain': 'kaali.in', 'roles': [{'name': 'HR', 'access': 'User'}]}, 'b@kaali.in', 'kaali.in', elevate=lambda: 'svc')
        self.assertEqual(out['roles'], [{'name': 'HR', 'access': 'User', 'perms': []}])
        self.assertEqual(a.calls[-1][0], 'ModifyDomainRequest'); self.assertEqual(a.calls[-1][2], 'svc')

    def test_company_admin_stays_in_own_domain(self):
        a = Fake()
        with self.assertRaises(z.APIError): a.action('t', {'op': 'save_roles', 'domain': 'other.in', 'roles': [{'name': 'x'}]}, 'b@kaali.in', 'kaali.in')
        with self.assertRaises(z.APIError): a.action('t', {'op': 'create_department', 'name': 'X', 'email': 'x@other.in'}, 'b@kaali.in', 'kaali.in')
        with self.assertRaises(z.APIError): a.action('t', {'op': 'save_roles', 'domain': 'kaali.in', 'roles': [{'name': 'Boss', 'access': 'Admin'}]}, 'b@kaali.in', 'kaali.in')

    def test_default_roles(self):
        self.assertEqual(z.read_roles('')[0]['name'], 'Member')
        # saved before @all needed a permission: the role keeps @all, as it had
        self.assertEqual(z.read_roles('{"dejoiyRoles":[{"name":"HR","access":"User"}]}'), [{'name': 'HR', 'access': 'User', 'perms': ['mail.everyone']}])

    def test_role_permissions_limit_company_admins(self):
        a = Fake()
        with self.assertRaisesRegex(z.APIError, 'does not allow'):
            a.action('t', {'op': 'delete_user', 'id': USER, 'confirm': 'ravi@kaali.in'}, 'b@kaali.in', 'kaali.in', perms={'mailboxes.manage'})
        a.action('t', {'op': 'set_title', 'id': USER, 'title': 'HR'}, 'b@kaali.in', 'kaali.in', perms={'roles.manage'})
        a.action('t', {'op': 'set_title', 'id': USER, 'title': 'HR'}, 'root@dejoiy.com', None, perms={'nothing'})  # platform admins are not limited

    def test_console_permissions_need_admin_access(self):
        with self.assertRaisesRegex(z.APIError, 'company admin access'):
            Fake().action('t', {'op': 'save_roles', 'domain': 'kaali.in', 'roles': [{'name': 'HR', 'access': 'User', 'perms': ['mailboxes.delete']}]}, 'b@kaali.in', 'kaali.in', elevate=lambda: 'svc')

    def test_role_perms_owner_and_members(self):
        roles = z.read_roles('')
        self.assertEqual(z.role_perms(roles, '', True), set(z.PERMISSIONS))          # company owner without a role
        self.assertEqual(z.role_perms(roles, 'Member', False), {'mail.everyone'})
        self.assertEqual(z.role_perms(roles, 'team lead', False), {'mail.everyone', 'updates.post'})
        self.assertEqual(z.role_perms(roles, 'Nobody', False), set())
        notes = z.write_org('', boxName='Kaali Tea News')
        self.assertEqual(z.read_org(notes)['boxName'], 'Kaali Tea News')

if __name__ == '__main__': unittest.main()


class CompactOrg(unittest.TestCase):
    """Roles and policies are stored in a short form, because the mail server keeps a domain's notes to about 1024 characters."""
    def test_thirty_roles_fit_and_come_back_the_same(self):
        roles = [{'name': f'Quality Analyst {i:02d}', 'access': 'Domain admin' if i % 3 == 0 else 'User',
                  'perms': sorted(z.PERMISSIONS) if i % 3 == 0 else (['tickets.manage', 'updates.post'] if i % 2 else [])} for i in range(30)]
        notes = z.write_org('', roles=roles)
        self.assertLessEqual(len(notes), z.ORG_NOTES_LIMIT)
        self.assertEqual(z.read_org(notes)['roles'], roles)
    def test_old_long_form_is_still_read_and_policies_survive(self):
        old = json.dumps({'dejoiyRoles': [{'name': 'CEO', 'access': 'Domain admin', 'perms': ['roles.manage', 'updates.post']}], 'companyBox': 'Notice board',
                          'mailPolicies': [{'name': 'Strict', 'rules': {**z.standard_policy()['rules'], 'forwarding': False, 'trashDays': 14}}], 'defaultPolicy': 'Strict'})
        before = z.read_org(old); after = z.read_org(z.write_org(old))
        self.assertEqual(after, before); self.assertEqual(after['policies'][0]['rules']['forwarding'], False); self.assertEqual(after['boxName'], 'Notice board')
    def test_too_much_is_refused_with_a_reason(self):
        roles = [{'name': 'x' * 40 + str(i), 'access': 'User', 'perms': []} for i in range(30)]
        with self.assertRaises(z.APIError): z.write_org('', roles=roles)


class ShineRoles(unittest.TestCase):
    """The Shine permissions that mean something in mail: @all for the whole company and the reports page."""
    def test_old_saved_roles_keep_what_they_could_do(self):
        old = json.dumps({'r': [['Agent', 0, 0], ['IT', 1, 0b1111110]], 'b': '', 'd': 'Standard', 'p': []})   # saved before version 2
        agent, it = z.read_roles(old)
        self.assertEqual(agent['perms'], ['mail.everyone'])                       # everyone could use @all
        self.assertIn('reports.view', it['perms'])                               # every company admin saw reports
    def test_new_saves_keep_a_ticked_off_permission_off(self):
        roles = [{'name': 'Agent', 'access': 'User', 'perms': []}, {'name': 'IT', 'access': 'Domain admin', 'perms': ['mailboxes.manage']}]
        self.assertEqual(z.read_roles(z.write_org('', roles=roles)), roles)
    def test_shine_roles_are_valid_and_fit_next_to_many_roles(self):
        for r in z.SHINE_ROLES:
            self.assertTrue(set(r['perms']) <= set(z.PERMISSIONS))
            if r['access'] == 'User': self.assertFalse(set(r['perms']) & z.CONSOLE_PERMISSIONS, r['name'])
        bpo = [{'name': f'Quality Analyst {i:02d}', 'access': 'User', 'perms': ['tickets.manage']} for i in range(19)]
        notes = z.write_org('', roles=bpo + z.SHINE_ROLES)
        self.assertLessEqual(len(notes), z.ORG_NOTES_LIMIT)
        self.assertEqual(z.read_roles(notes)[-1]['name'], 'Employee')
    def test_mail_everyone_is_a_mail_permission(self):
        self.assertNotIn('mail.everyone', z.CONSOLE_PERMISSIONS); self.assertIn('reports.view', z.CONSOLE_PERMISSIONS)
        self.assertEqual(z.PERM_ORDER[:7], ('updates.post', 'mailboxes.manage', 'mailboxes.delete', 'teams.manage', 'domain.view', 'roles.manage', 'tickets.manage'))

class AtAll(unittest.TestCase):
    def run_mention(self, perms):
        me = type('H', (), {})()
        me.org = lambda s: {'perms': perms}; me.domain = lambda s: 'kaali.in'
        me.mailboxes = lambda: [{'email': e, 'active': True, 'a': {}} for e in ('me@kaali.in', 'a@kaali.in', 'b@other.in')]
        return z.Handler.mention_recipients(me, {'user': {'email': 'me@kaali.in'}}, {'to': '@all', 'body': 'hi'})
    def test_all_needs_the_permission(self):
        with self.assertRaisesRegex(z.APIError, 'does not allow'): self.run_mention([])
        out = self.run_mention(['mail.everyone'])
        self.assertEqual(out['bcc'], 'a@kaali.in'); self.assertEqual(out['to'], 'me@kaali.in')
