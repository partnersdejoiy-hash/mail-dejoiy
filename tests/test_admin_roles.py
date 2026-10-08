import sys, unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import zimbra as z
ID='12345678-1234-1234-1234-123456789012'
def response(text):return z.ET.fromstring(text)
def account(email='owner@example.com',admin='TRUE'):
    return response(f'<GetAccountResponse xmlns="urn:zimbraAdmin"><account name="{email}"><a n="zimbraIsAdminAccount">{admin}</a></account></GetAccountResponse>')
class RolesTests(unittest.TestCase):
    def client(self):
        c=z.Admin('https://mail.example.com:7071');c.call=Mock(return_value=response('<Response xmlns="urn:zimbraAdmin"/>'));return c
    def test_capabilities_fail_closed_for_missing_attributes(self):
        c=z.Zimbra('https://mail.example.com');c.call=Mock(return_value=response('<GetInfoResponse xmlns="urn:zimbraAccount"/>'))
        self.assertEqual(c.capabilities('t'),{'isAdmin':False,'canManageRoles':False})
    def test_capabilities_distinguish_full_and_delegated_admin(self):
        for attribute,can_manage in [('zimbraIsAdminAccount',True),('zimbraIsDelegatedAdminAccount',False)]:
            c=z.Zimbra('https://mail.example.com');c.call=Mock(return_value=response(f'<GetInfoResponse xmlns="urn:zimbraAccount"><attrs><attr name="{attribute}">TRUE</attr></attrs></GetInfoResponse>'))
            self.assertEqual(c.capabilities('t'),{'isAdmin':True,'canManageRoles':can_manage})
    def test_default_mailbox_is_not_admin(self):
        c=self.client();c.action('t',{'op':'create_user','email':'new@example.com','name':'New','password':'test'},'owner@example.com')
        request=c.call.call_args.args[0];attrs={a.get('n'):a.text for a in request.findall('{'+z.ADMIN+'}a')}
        self.assertEqual(attrs['zimbraIsAdminAccount'],'FALSE');self.assertEqual(c.call.call_count,1)
    def test_admin_creation_checks_actor_against_upstream(self):
        c=self.client();c.call.side_effect=[account(),response('<Response/>')]
        c.action('t',{'op':'create_user','email':'new@example.com','name':'New','password':'test','role':'Admin'},'owner@example.com')
        request=c.call.call_args.args[0];self.assertTrue(any(a.get('n')=='zimbraIsAdminAccount' and a.text=='TRUE' for a in request))
    def test_delegated_admin_cannot_grant_full_admin(self):
        c=self.client();c.call.return_value=account(admin='FALSE')
        with self.assertRaises(z.APIError):c.action('t',{'op':'create_user','email':'new@example.com','name':'New','password':'test','role':'Admin'},'owner@example.com')
        self.assertEqual(c.call.call_count,1)
    def test_invalid_role_is_rejected_without_upstream_mutation(self):
        c=self.client()
        with self.assertRaises(z.APIError):c.action('t',{'op':'create_user','email':'new@example.com','role':'Superuser'},'owner@example.com')
        c.call.assert_not_called()
    def test_cannot_change_own_role(self):
        c=self.client();c.call.return_value=account()
        with self.assertRaises(z.APIError):c.action('t',{'op':'role','id':ID,'role':'User'},'owner@example.com')
        self.assertEqual(c.call.call_count,1)
    def test_role_demotion_clears_both_admin_flags(self):
        c=self.client();c.call.side_effect=[account('other@example.com'),account(),response('<Response/>')]
        c.action('t',{'op':'role','id':ID,'role':'User'},'owner@example.com')
        attrs={a.get('n'):a.text for a in c.call.call_args.args[0].findall('{'+z.ADMIN+'}a')}
        self.assertEqual(attrs,{'zimbraIsAdminAccount':'FALSE','zimbraIsDelegatedAdminAccount':'FALSE'})
    def test_quota_converts_megabytes_and_rejects_bad_values(self):
        c=self.client();c.call.return_value=account('other@example.com')
        c.action('t',{'op':'quota','id':ID,'quotaMB':512},'owner@example.com')
        self.assertEqual(c.call.call_args.args[0].find('{'+z.ADMIN+'}a').text,str(512*1048576))
        for quota in [-1,True,'100',1.5,10485761]:
            c.call.reset_mock()
            with self.assertRaises(z.APIError):c.action('t',{'op':'quota','id':ID,'quotaMB':quota},'owner@example.com')
            self.assertEqual(c.call.call_count,1)
    def test_alias_request_uses_explicit_operation_and_validates_address(self):
        c=self.client();c.call.return_value=account('other@example.com')
        for op,request in [('add_alias','AddAccountAliasRequest'),('remove_alias','RemoveAccountAliasRequest')]:
            c.action('t',{'op':op,'id':ID,'alias':' Alias@Example.com '},'owner@example.com')
            self.assertEqual(c.call.call_args.args[0].tag,'{'+z.ADMIN+'}'+request)
            self.assertEqual(c.call.call_args.args[0].find('{'+z.ADMIN+'}alias').text,'alias@example.com')
        c.call.reset_mock()
        with self.assertRaises(z.APIError):c.action('t',{'op':'add_alias','id':ID,'alias':'invalid'},'owner@example.com')
        self.assertEqual(c.call.call_count,1)
if __name__=='__main__':unittest.main()
