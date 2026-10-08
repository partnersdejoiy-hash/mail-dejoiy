import sys
import tempfile
import json
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import zimbra as z

class Response:
    def __init__(self,body): self.body=body
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return self.body

class AdapterTests(unittest.TestCase):
    def test_https_only(self):
        with self.assertRaises(ValueError): z.Zimbra('http://mail.example.com')
    def test_token_stays_in_server_request(self):
        client=z.Zimbra('https://mail.example.com')
        client.opener=Mock(); client.opener.open.return_value=Response(b'<Envelope xmlns="http://www.w3.org/2003/05/soap-envelope"><Body><SendMsgResponse xmlns="urn:zimbraMail"/></Body></Envelope>')
        client.call(z.node(z.MAIL,'SendMsgRequest'),'secret-token')
        req=client.opener.open.call_args.args[0]
        self.assertEqual(z.ET.fromstring(req.data).find('.//{urn:zimbra}authToken').text,'secret-token')
    def test_upstream_auth_fault(self):
        client=z.Zimbra('https://mail.example.com'); client.opener=Mock()
        client.opener.open.return_value=Response(b'<Envelope xmlns="http://www.w3.org/2003/05/soap-envelope"><Body><Fault><Detail><Error xmlns="urn:zimbra"><Code>account.AUTH_FAILED</Code></Error></Detail></Fault></Body></Envelope>')
        with self.assertRaises(z.APIError) as caught: client.call(z.node(z.ACCOUNT,'AuthRequest'))
        self.assertEqual(caught.exception.status,401)
    def test_mail_body_cannot_inject_html(self):
        client=z.Zimbra('https://mail.example.com')
        responses=[z.ET.fromstring('<GetFolderResponse xmlns="urn:zimbraMail"><folder id="1"/></GetFolderResponse>'),z.ET.fromstring('<SearchResponse xmlns="urn:zimbraMail" more="1"><m id="11"/></SearchResponse>'),z.ET.fromstring('<GetMsgResponse xmlns="urn:zimbraMail"><m id="11" l="2" d="12" f="u"><e t="f" a="a@b.com"/><su>Hello</su><mp ct="text/plain"><content>&lt;img src=x onerror=alert(1)&gt;</content></mp></m></GetMsgResponse>')]
        client.call=Mock(side_effect=responses); result=client.messages('token')
        self.assertEqual(client.call.call_args_list[1].args[0].find('{urn:zimbraMail}query').text, 'is:anywhere')
        self.assertIn('&lt;img',result['emails'][0]['body']);self.assertTrue(result['more']);self.assertFalse(result['emails'][0]['read'])
    def test_send_escapes_and_uses_authenticated_sender(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock(return_value=z.ET.fromstring('<SendMsgResponse xmlns="urn:zimbraMail"><m id="42"/></SendMsgResponse>'))
        out=client.write_message('token',{'to':'a@b.com','subject':'A & B','body':'<b>Hello</b><script>bad()</script>'})
        request=client.call.call_args.args[0]
        self.assertEqual(out['id'],'42');self.assertEqual(request.find('.//{urn:zimbraMail}content').text,'Hello')
        self.assertEqual(len(request.findall('.//{urn:zimbraMail}e')),1)
    def test_attachment_rejected_instead_of_silent_loss(self):
        client=z.Zimbra('https://mail.example.com')
        with self.assertRaises(z.APIError):client.write_message('t',{'to':'a@b.com','attachments':[{'name':'file.pdf'}]})
    def test_gmail_typo_rejected_before_mail_submission(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock()
        with self.assertRaisesRegex(z.APIError,'Gmail'):
            client.write_message('t',{'to':'recipient!@gmail.com'})
        client.call.assert_not_called()
        client.call.return_value=z.ET.fromstring('<SendMsgResponse xmlns="urn:zimbraMail"><m id="42"/></SendMsgResponse>')
        client.write_message('t',{'to':'recipient+tag@gmail.com'})
    def test_attachments_and_draft_cleanup_are_submitted_atomically(self):
        client=z.Zimbra('https://mail.example.com')
        client.upload=Mock(return_value='server:upload')
        client.call=Mock(return_value=z.ET.fromstring('<SendMsgResponse xmlns="urn:zimbraMail"><m id="42"/></SendMsgResponse>'))
        result=client.write_message('t',{'id':'12','to':'a@b.com','attachments':[{'name':'x.txt','data':'aGVsbG8=','type':'text/plain'},{'name':'old.txt','mid':'12','part':'2'}]})
        m=client.call.call_args.args[0][0]
        self.assertEqual(m.get('did'),'12');self.assertTrue(result['draftRemoved'])
        self.assertEqual(m.find('{urn:zimbraMail}attach').get('aid'),'server:upload')
        self.assertEqual(m.find('.//{urn:zimbraMail}attach/{urn:zimbraMail}mp').get('mid'),'12')
    def test_attachment_upload_failure_prevents_send(self):
        client=z.Zimbra('https://mail.example.com');client.upload=Mock(side_effect=z.APIError('Upload failed'));client.call=Mock()
        with self.assertRaises(z.APIError):client.write_message('t',{'to':'a@b.com','attachments':[{'name':'x.txt','data':'aGVsbG8='}]})
        client.call.assert_not_called()
    def test_rich_html_keeps_formatting_and_removes_active_content(self):
        body=z.safe_html('<b onclick="bad()">Hello</b><script>bad()</script><img src="https://tracker"><a href="javascript:bad()">Link</a><a href="https://example.com">Safe</a>')
        self.assertIn('<b>Hello</b>',body);self.assertIn('https://example.com',body)
        for forbidden in ('script','onclick','javascript:','tracker','bad()'):self.assertNotIn(forbidden,body)
    def test_action_validation(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock()
        with self.assertRaises(z.APIError):client.action('t',{'ids':['1,2'],'op':'delete'})
        client.action('t',{'ids':['1'],'op':'read','value':False})
        self.assertEqual(client.call.call_args.args[0][0].get('op'),'!read')
    def test_contacts_validation_and_attribute_mapping(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock(return_value=z.ET.fromstring('<GetContactsResponse xmlns="urn:zimbraMail"><cn id="12"><a n="fullName">Alice</a><a n="email">alice@example.com</a><a n="mobilePhone">123</a></cn></GetContactsResponse>'))
        contact=client.contacts('token')['contacts'][0]
        self.assertEqual(contact['name'],'Alice');self.assertEqual(contact['phone'],'123')
        client.call.reset_mock()
        with self.assertRaises(z.APIError):client.contact_action('token',{'op':'delete','id':'12,13'})
        with self.assertRaises(z.APIError):client.contact_action('token',{'op':'save','name':'Alice','email':'invalid'})
        client.call.assert_not_called()
    def test_preferences_reject_unknown_fields_and_non_boolean_toggle(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock()
        for data in ({'op':'unknown'},{'op':'vacation','on':'false'},{'op':'profile','name':''}):
            with self.assertRaises(z.APIError):client.save_preferences('token',data)
        client.call.assert_not_called()

class SessionTests(unittest.TestCase):
    def test_restart_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'sessions.sqlite')
            store = z.SessionStore(path)
            store['opaque-id'] = {'token':'private', 'expires':123}
            store.db.close()
            store = z.SessionStore(path)
            self.assertEqual(store['opaque-id']['token'], 'private')
            self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
            del store['opaque-id']
            self.assertEqual(len(store), 0)
            store.db.close()

class AdminTests(unittest.TestCase):
    def client(self, response):
        client=z.Admin('https://mail.example.com:7071')
        client.call=Mock(return_value=z.ET.fromstring(response))
        return client
    def test_admin_login_uses_separate_endpoint_and_namespace(self):
        client=self.client('<AuthResponse xmlns="urn:zimbraAdmin"><authToken>private-admin</authToken><lifetime>3600000</lifetime></AuthResponse>')
        self.assertEqual(client.login('admin@example.com','secret'),('private-admin',900))
        self.assertEqual(client.url,'https://mail.example.com:7071/service/admin/soap/')
        self.assertEqual(client.call.call_args.args[0].tag,'{urn:zimbraAdmin}AuthRequest')
    def test_admin_response_does_not_expose_private_attributes(self):
        client=self.client('<GetAllAccountsResponse xmlns="urn:zimbraAdmin"><account id="id" name="a@example.com"><a n="displayName">Alice</a><a n="userPassword">HASH-SECRET</a></account></GetAllAccountsResponse>')
        client.call.side_effect=[client.call.return_value,z.ET.fromstring('<GetAllDomainsResponse xmlns="urn:zimbraAdmin"><domain id="domain-id" name="example.com"/></GetAllDomainsResponse>')]
        result=client.overview('token')
        self.assertEqual(result['users'][0]['name'],'Alice')
        self.assertNotIn('HASH-SECRET',json.dumps(result))
    def test_cannot_lock_own_admin_mailbox(self):
        client=self.client('<GetAccountResponse xmlns="urn:zimbraAdmin"><account name="admin@example.com"/></GetAccountResponse>')
        with self.assertRaises(z.APIError):
            client.action('token',{'op':'status','id':'12345678-1234-1234-1234-123456789012','status':'locked'},'admin@example.com')
        self.assertEqual(client.call.call_count,1)
    def test_provisioning_rejects_bad_domain_and_unknown_operation(self):
        client=self.client('<CreateDomainResponse xmlns="urn:zimbraAdmin"/>')
        for data in ({'op':'create_domain','domain':'bad domain'},{'op':'delete_user'},{'op':'status','id':'x','status':'active'}):
            with self.assertRaises(z.APIError):client.action('token',data,'admin@example.com')
        client.call.assert_not_called()

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server.attempts={}
    @classmethod
    def setUpClass(cls):
        cls.server=z.ThreadingHTTPServer(('127.0.0.1',0),z.Handler)
        cls.url='http://127.0.0.1:'+str(cls.server.server_port);cls.server.app_origin=cls.url;cls.server.attempts={}
        cls.server.zimbra=Mock();cls.server.zimbra.login.return_value=('private-token',3600);cls.server.zimbra.messages.return_value={'emails':[]};cls.server.zimbra.write_message.return_value={'id':'42'}
        cls.server.admin=Mock();cls.server.admin.login.return_value=('private-admin-token',900);cls.server.admin.overview.return_value={'users':[],'domains':[]};cls.server.admin.action.return_value={'ok':True}
        cls.server.zimbra.contacts.return_value={'contacts':[]};cls.server.zimbra.contact_action.return_value={'id':'12','ok':True}
        cls.server.zimbra.preferences.return_value={'name':'Test','signature':'','vacation':{'on':False,'message':''}};cls.server.zimbra.save_preferences.return_value={'ok':True}
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close()
    def request(self,path,data=None,cookie=None,csrf=None,origin=None):
        headers={}
        if cookie:headers['Cookie']=cookie
        if csrf:headers['X-CSRF-Token']=csrf
        if data is not None:headers.update({'Content-Type':'application/json','Origin':origin or self.url})
        req=urllib.request.Request(self.url+path,None if data is None else json.dumps(data).encode(),headers)
        try:
            with urllib.request.urlopen(req) as response:
                raw=response.read().decode()
                return response.status,json.loads(raw) if response.headers.get_content_type()=='application/json' else raw,response.headers
        except urllib.error.HTTPError as e:
            raw=e.read().decode()
            return e.code,json.loads(raw) if e.headers.get_content_type()=='application/json' else raw,e.headers
    def login(self,email):
        status,data,headers=self.request('/api/login',{'email':email,'password':'test'})
        self.assertEqual(status,200);self.assertNotIn('private-token',json.dumps(data));self.assertIn('HttpOnly',headers['Set-Cookie'])
        return headers['Set-Cookie'].split(';')[0],data['csrf']
    def test_auth_csrf_and_logout(self):
        self.assertEqual(self.request('/api/mail')[0],401)
        cookie,csrf=self.login('one@example.com')
        self.assertEqual(self.request('/api/send',{'to':'a@b.com'},cookie)[0],403)
        self.assertEqual(self.request('/api/send',{'to':'a@b.com'},cookie,csrf,'https://evil.example')[0],403)
        self.assertEqual(self.request('/api/send',{'to':'a@b.com'},cookie,csrf)[0],200)
        self.assertEqual(self.request('/api/logout',{},cookie,csrf)[0],200)
        self.assertEqual(self.request('/api/mail',cookie=cookie)[0],401)
    def test_accounts_are_isolated(self):
        one,_=self.login('one@example.com');two,_=self.login('two@example.com')
        self.assertEqual(self.request('/api/session',cookie=one)[1]['user']['email'],'one@example.com')
        self.assertEqual(self.request('/api/session',cookie=two)[1]['user']['email'],'two@example.com')
    def test_static_exposes_only_web_directory(self):
        self.assertEqual(self.request('/../server/zimbra.py')[0],404)
    def test_admin_requires_csrf_and_separate_authorization(self):
        cookie,csrf=self.login('admin@example.com')
        self.assertEqual(self.request('/api/admin',cookie=cookie)[0],403)
        self.assertEqual(self.request('/api/admin/action',{'op':'create_domain'},cookie,csrf)[0],403)
        self.assertEqual(self.request('/api/admin/login',{'password':'secret'},cookie)[0],403)
        status,data,_=self.request('/api/admin/login',{'password':'secret'},cookie,csrf)
        self.assertEqual(status,200);self.assertNotIn('private-admin-token',json.dumps(data))
        self.assertEqual(self.request('/api/admin',cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/admin/action',{'op':'create_domain'},cookie,csrf)[0],200)
        self.assertEqual(self.request('/api/admin/logout',{},cookie,csrf)[0],200)
        self.assertEqual(self.request('/api/admin',cookie=cookie)[0],403)
    def test_admin_authorization_is_isolated_between_sessions(self):
        one,csrf=self.login('admin@example.com');two,_=self.login('other@example.com')
        self.assertEqual(self.request('/api/admin/login',{'password':'secret'},one,csrf)[0],200)
        self.assertEqual(self.request('/api/admin',cookie=two)[0],403)
    def test_config_and_admin_page_use_product_brand(self):
        self.assertEqual(self.request('/api/config')[1]['mode'],'live')
        self.assertIn('Dejoiy Mail',self.request('/admin')[1])
    def test_mail_pagination_rejects_invalid_offsets(self):
        cookie,_=self.login('paging@example.com')
        self.assertEqual(self.request('/api/mail?offset=50',cookie=cookie)[0],200)
        self.server.zimbra.messages.assert_called_with('private-token',50)
        for value in ('-1','abc','1000001'):
            self.assertEqual(self.request('/api/mail?offset='+value,cookie=cookie)[0],400)
    def test_contacts_and_preferences_require_session_and_csrf(self):
        for path in ('/api/contacts','/api/preferences'):self.assertEqual(self.request(path)[0],401)
        cookie,csrf=self.login('preferences@example.com')
        self.assertEqual(self.request('/api/contacts',cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/contacts',{'op':'save'},cookie)[0],403)
        self.assertEqual(self.request('/api/contacts',{'op':'save'},cookie,csrf)[0],200)
        self.assertEqual(self.request('/api/preferences',{'op':'profile'},cookie)[0],403)
        self.assertEqual(self.request('/api/preferences',{'op':'profile'},cookie,csrf)[0],200)
    def test_login_rate_limit_is_enforced(self):
        for _ in range(10):self.assertEqual(self.request('/api/login',{'email':'limited@example.com','password':'test'})[0],200)
        self.assertEqual(self.request('/api/login',{'email':'limited@example.com','password':'test'})[0],429)

if __name__=='__main__':unittest.main()
