"""Departments and roles in the admin console, against a fake mail server."""
import os, sys, unittest
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
        self.assertEqual(out['roles'], [{'name': 'HR', 'access': 'User'}])
        self.assertEqual(a.calls[-1][0], 'ModifyDomainRequest'); self.assertEqual(a.calls[-1][2], 'svc')

    def test_company_admin_stays_in_own_domain(self):
        a = Fake()
        with self.assertRaises(z.APIError): a.action('t', {'op': 'save_roles', 'domain': 'other.in', 'roles': [{'name': 'x'}]}, 'b@kaali.in', 'kaali.in')
        with self.assertRaises(z.APIError): a.action('t', {'op': 'create_department', 'name': 'X', 'email': 'x@other.in'}, 'b@kaali.in', 'kaali.in')
        with self.assertRaises(z.APIError): a.action('t', {'op': 'save_roles', 'domain': 'kaali.in', 'roles': [{'name': 'Boss', 'access': 'Admin'}]}, 'b@kaali.in', 'kaali.in')

    def test_default_roles(self):
        self.assertEqual(z.read_roles('')[0]['name'], 'Member')
        self.assertEqual(z.read_roles('{"dejoiyRoles":[{"name":"HR","access":"User"}]}'), [{'name': 'HR', 'access': 'User'}])

if __name__ == '__main__': unittest.main()
