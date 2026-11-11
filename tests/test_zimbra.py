import base64
from types import SimpleNamespace
import sys
import tempfile
import json
import time
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

class DnsRecordTests(unittest.TestCase):
    def lookup(self, answers):
        return lambda name, kind='TXT': answers.get((name,kind),[])
    def test_spf_is_merged_not_duplicated(self):
        self.assertEqual(z.merged_spf('v=spf1 include:_spf.google.com -all','mail.dejoiy.com'),'v=spf1 include:_spf.google.com mx a:mail.dejoiy.com include:amazonses.com -all')
        self.assertEqual(z.merged_spf('','mail.dejoiy.com'),'v=spf1 mx a:mail.dejoiy.com include:amazonses.com ~all')
    def test_all_records_with_conflicts(self):
        old=z.dns_lookup
        z.dns_lookup=self.lookup({('acme.com','MX'):['mail.dejoiy.com','mx.zoho.in'],('acme.com','TXT'):['v=spf1 include:zoho.in ~all','v=spf1 mx ~all']})
        try: rec={r['kind']:r for r in z.domain_records('acme.com','mail.dejoiy.com',None)}
        finally: z.dns_lookup=old
        self.assertEqual(list(rec),['MX','SPF','DKIM','DMARC'])
        self.assertEqual(rec['MX']['status'],'conflict');self.assertIn('mx.zoho.in',rec['MX']['note'])
        self.assertEqual(rec['SPF']['status'],'conflict');self.assertTrue(rec['DKIM']['pending']);self.assertEqual(rec['DMARC']['status'],'missing')
    def test_signup_lists_proof_first_and_survives_dns_outage(self):
        old=z.dns_lookup
        def down(*a,**k): raise z.APIError('DNS down',502)
        z.dns_lookup=down
        try: records=z.signup_records({'domain':'acme.com','code':'dejoiy-verification=x'},'mail.dejoiy.com',None)
        finally: z.dns_lookup=old
        self.assertEqual([r['kind'] for r in records],['Verification'])
        z.dns_lookup=self.lookup({('acme.com','MX'):['mail.dejoiy.com'],('acme.com','TXT'):['v=spf1 mx a:mail.dejoiy.com include:amazonses.com ~all'],('_dmarc.acme.com','TXT'):['v=DMARC1; p=none']})
        try: records=z.signup_records({'domain':'acme.com','code':'dejoiy-verification=x'},'mail.dejoiy.com',None)
        finally: z.dns_lookup=old
        self.assertEqual([r['kind'] for r in records],['Verification','MX','SPF','DKIM','DMARC'])
        self.assertTrue(all(r['ok'] for r in records if r['kind'] in ('MX','SPF','DMARC')))


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
        self.assertEqual(client.call.call_args_list[2].args[0][0].get('html'),'1')
        self.assertIn('&lt;img',result['emails'][0]['body']);self.assertTrue(result['more']);self.assertFalse(result['emails'][0]['read'])
    def test_send_escapes_and_uses_authenticated_sender(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock(return_value=z.ET.fromstring('<SendMsgResponse xmlns="urn:zimbraMail"><m id="42"/></SendMsgResponse>'))
        out=client.write_message('token',{'to':'a@b.com','subject':'A & B','body':'<b>Hello</b><script>bad()</script>'})
        request=client.call.call_args.args[0]
        parts=request.findall('.//{urn:zimbraMail}content')
        self.assertEqual(out['id'],'42');self.assertTrue(parts[0].text.startswith('Hello\n\n--\nThis mail is being sent using Dejoiy Mail'))
        self.assertNotIn('<script',parts[1].text);self.assertIn('data-dejoiy-mail',parts[1].text);self.assertIn('href="https://mail.dejoiy.com"',parts[1].text)
        self.assertEqual(len(request.findall('.//{urn:zimbraMail}e')),1)
    def test_joi_mailbox_sends_in_joi_look(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock(return_value=z.ET.fromstring('<SendMsgResponse xmlns="urn:zimbraMail"><m id="42"/></SendMsgResponse>'))
        client.write_message('token',{'to':'a@b.com','subject':'Hi','body':'Hello there'},sender='Joi-AI@mail.dejoiy.com')
        text,markup=[c.text for c in client.call.call_args.args[0].findall('.//{urn:zimbraMail}content')]
        self.assertIn('joi-peek.gif',markup);self.assertIn('dmail-logo.gif',markup);self.assertIn('Powered by',markup);self.assertNotIn('banner-',markup)
        self.assertIn('Love,\nJoi',text)
        client.write_message('token',{'to':'a@b.com','subject':'Hi','body':'Hello'},sender='deepak@dejoiy.com')
        self.assertNotIn('joi-peek.gif',client.call.call_args.args[0].findall('.//{urn:zimbraMail}content')[1].text)
    def test_sent_mail_takes_label_colour(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock(return_value=z.ET.fromstring('<SendMsgResponse xmlns="urn:zimbraMail"><m id="42"/></SendMsgResponse>'))
        client.write_message('token',{'to':'a@b.com','subject':'Invoice','body':'Hi','label':'Money','important':True})
        request=client.call.call_args_list[0].args[0]
        self.assertIn('banner-money.gif',request.findall('.//{urn:zimbraMail}content')[1].text)
        self.assertEqual(request.find('.//{urn:zimbraMail}m').get('f'),'!')
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

class DeleteDomainTests(unittest.TestCase):
    ID='12345678-1234-1234-1234-123456789012'
    def client(self, *responses):
        client=z.Admin('https://mail.example.com:7071')
        client.call=Mock(side_effect=[z.ET.fromstring(r) if isinstance(r,str) else r for r in responses])
        return client
    FOUND='<GetDomainResponse xmlns="urn:zimbraAdmin"><domain id="x" name="old.example.com"/></GetDomainResponse>'
    def test_deletes_an_empty_domain_after_typed_confirmation(self):
        client=self.client(self.FOUND,'<DeleteDomainResponse xmlns="urn:zimbraAdmin"/>')
        out=client.action('token',{'op':'delete_domain','id':self.ID,'confirm':'Old.Example.com'},'admin@example.com')
        self.assertEqual(out,{'ok':True,'deleted':'old.example.com'})
        self.assertEqual(client.call.call_args.args[0].tag,'{urn:zimbraAdmin}DeleteDomainRequest')
    def test_needs_the_name_typed(self):
        client=self.client(self.FOUND)
        with self.assertRaises(z.APIError): client.action('token',{'op':'delete_domain','id':self.ID,'confirm':'nope'},'admin@example.com')
        self.assertEqual(client.call.call_count,1)
    def test_not_your_own_domain(self):
        client=self.client(self.FOUND)
        with self.assertRaises(z.APIError): client.action('token',{'op':'delete_domain','id':self.ID,'confirm':'old.example.com'},'boss@old.example.com')
    def test_company_admins_cannot_delete_domains(self):
        client=self.client()
        with self.assertRaises(z.APIError) as e: client.action('token',{'op':'delete_domain','id':self.ID,'confirm':'x'},'a@acme.com','acme.com')
        self.assertEqual(e.exception.status,403); client.call.assert_not_called()
    def test_domain_with_mailboxes_explains_what_to_do(self):
        client=self.client(self.FOUND,z.APIError('x',500,'account.DOMAIN_NOT_EMPTY'))
        with self.assertRaises(z.APIError) as e: client.action('token',{'op':'delete_domain','id':self.ID,'confirm':'old.example.com'},'admin@example.com')
        self.assertEqual(e.exception.status,409); self.assertIn('Delete them first',str(e.exception))

class PresenceTests(unittest.TestCase):
    def handler(self, answer):
        h=z.Handler.__new__(z.Handler)
        h.server=SimpleNamespace(shine_secret='secret',shine_site='https://shine.example')
        h.shine_post=Mock(return_value=answer)
        return h
    SESSION={'user':{'email':'Deepak@Dejoiy.com'}}
    def test_heartbeat_and_status_go_to_shine_for_your_own_mailbox(self):
        h=self.handler({'choice':'busy','text':'In a meeting'})
        out=h.presence(self.SESSION,{'idle':False,'choice':'busy','text':'In a meeting','email':'someone@else.com'})
        self.assertEqual(out,{'enabled':True,'choice':'busy','text':'In a meeting'})
        h.shine_post.assert_called_once_with('/dejoiy/presence',{'email':'deepak@dejoiy.com','idle':False,'choice':'busy','text':'In a meeting'})
    def test_unknown_choice_is_dropped(self):
        h=self.handler({'choice':'auto','text':''})
        h.presence(self.SESSION,{'choice':'sleeping'})
        self.assertNotIn('choice',h.shine_post.call_args.args[1])
    def test_without_shine_it_says_disabled(self):
        self.assertEqual(self.handler(None).presence(self.SESSION,{'idle':True}),{'enabled':False})
    def test_people_status_only_asks_about_colleagues_and_joi(self):
        h=self.handler({'people':{'a@dejoiy.com':{'status':'online','text':''}}})
        out=h.people_status(self.SESSION,{'emails':['a@dejoiy.com','A@dejoiy.com','x@gmail.com','joi-ai@mail.dejoiy.com','bad']})
        self.assertTrue(out['enabled'])
        h.shine_post.assert_called_once_with('/dejoiy/people',{'emails':['a@dejoiy.com','joi-ai@mail.dejoiy.com']})

class PhotoTests(unittest.TestCase):
    PNG='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'0'*40).decode()
    def handler(self):
        h=z.Handler.__new__(z.Handler)
        h.server=SimpleNamespace(shine_secret='secret',app_origin='https://mail.example',avatars=z.AvatarStore())
        return h
    def test_photos_are_shared_across_domains(self):
        h=self.handler(); h.server.avatars.put('a@one.com','png',b'x'); h.server.avatars.put('b@two.com','png',b'y')
        self.assertEqual(set(h.server.avatars.versions()),{'a@one.com','b@two.com'})
    def test_shine_upload_is_stored_and_gets_a_signed_public_link(self):
        h=self.handler()
        out=h.shine_avatar({'email':'Riya@Two.com','image':self.PNG})
        self.assertTrue(out['photo'].startswith('https://mail.example/api/public/avatar?e=riya%40two.com&s='))
        self.assertIsNotNone(h.server.avatars.get('riya@two.com'))
        self.assertEqual(h.shine_avatar({'email':'riya@two.com','image':''})['photo'],'')
        self.assertIsNone(h.server.avatars.get('riya@two.com'))
    def test_public_link_needs_the_right_signature(self):
        h=self.handler(); h.server.avatars.put('a@one.com','png',b'x')
        h.image=Mock(return_value='sent')
        h.path='/api/public/avatar?'+z.urllib.parse.urlencode({'e':'a@one.com','s':h.avatar_sig('a@one.com')})
        self.assertEqual(h.public_avatar(),'sent')
        h.path='/api/public/avatar?e=a%40one.com&s=forged'
        with self.assertRaises(z.APIError): h.public_avatar()
    def test_photo_set_only_in_shine_is_listed_and_copied_once(self):
        h=self.handler(); h.server.avatars.put('a@one.com','png',b'x')
        h.shine_post=Mock(return_value={'photos':{'B@Two.com':'https://convex.example/b.png','c@two.com':'http://plain'}})
        v=h.avatar_versions()
        self.assertEqual(set(v),{'a@one.com','b@two.com'}); self.assertTrue(v['b@two.com'].startswith('s'))
        png=b'\x89PNG\r\n\x1a\n'+b'0'*20
        class R:
            def __enter__(s): return s
            def __exit__(s,*a): pass
            def read(s,n): return png
        with unittest.mock.patch.object(z.urllib.request,'urlopen',return_value=R()):
            self.assertEqual(h.import_shine_photo('b@two.com'),('png',png))
        self.assertEqual(h.server.avatars.get('b@two.com'),('png',png))
        h.shine_post.assert_called_once()  # cached
    def test_joi_token_only_for_dejoiy_people_and_joi_can_check_it(self):
        h=self.handler(); h.server.joi_secret='joi-secret'; h.server.joi_internal=['dejoiy.com']; h.server.joi_url=h.server.joi_api='https://joi.example'
        out=h.joi({'user':{'email':'deepak@dejoiy.com'}})
        body,mac=out['token'].split('.')
        self.assertEqual(mac,z.b64u(z.hmac.new(b'joi-secret',body.encode(),z.hashlib.sha256).digest()))
        claims=json.loads(base64.urlsafe_b64decode(body+'=='))
        self.assertEqual(claims['app'],'mail'); self.assertGreater(claims['exp'],time.time()*1000)
        self.assertEqual(h.joi({'user':{'email':'riya@other.com'}})['token'],'')
    def test_supervisors_come_from_shine_and_bad_rows_are_dropped(self):
        h=self.handler(); session={'user':{'email':'Asha@One.com'}}
        h.shine_post=Mock(return_value={'people':[{'name':'Dev','email':'dev@two.com','title':'Team lead'},{'email':'nope'}]})
        self.assertEqual(h.supervisors(session),{'enabled':True,'people':[{'name':'Dev','email':'dev@two.com','title':'Team lead'}]})
        h.shine_post.assert_called_with('/dejoiy/supervisors',{'email':'asha@one.com'})
        h.shine_post=Mock(return_value=None)
        self.assertEqual(h.supervisors(session),{'enabled':False,'people':[]})

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
