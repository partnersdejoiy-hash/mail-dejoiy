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
    def test_action_validation(self):
        client=z.Zimbra('https://mail.example.com');client.call=Mock()
        with self.assertRaises(z.APIError):client.action('t',{'ids':['1,2'],'op':'delete'})
        client.action('t',{'ids':['1'],'op':'read','value':False})
        self.assertEqual(client.call.call_args.args[0][0].get('op'),'!read')

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

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=z.ThreadingHTTPServer(('127.0.0.1',0),z.Handler)
        cls.url='http://127.0.0.1:'+str(cls.server.server_port);cls.server.app_origin=cls.url;cls.server.attempts={}
        cls.server.zimbra=Mock();cls.server.zimbra.login.return_value=('private-token',3600);cls.server.zimbra.messages.return_value={'emails':[]};cls.server.zimbra.write_message.return_value={'id':'42'}
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
            with urllib.request.urlopen(req) as response:return response.status,json.load(response),response.headers
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

if __name__=='__main__':unittest.main()
