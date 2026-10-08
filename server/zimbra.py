"""Independent Dejoiy adapter for the Zimbra SOAP API. No upstream UI code."""
import html
import json
import os
import re
import secrets
import time
import threading
import sqlite3
import ipaddress
from collections.abc import MutableMapping
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from html.parser import HTMLParser

SOAP = 'http://www.w3.org/2003/05/soap-envelope'
MAIL = 'urn:zimbraMail'
ACCOUNT = 'urn:zimbraAccount'
FOLDERS = {'inbox':'2','sent':'5','drafts':'6','spam':'4','trash':'3'}
class SessionStore(MutableMapping):
    """Private SQLite token store; parent directory must be owned by the service."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.db.commit()
    def __getitem__(self, key):
        row = self.db.execute('SELECT data FROM sessions WHERE id=?', (key,)).fetchone()
        if row is None: raise KeyError(key)
        return json.loads(row[0])
    def __setitem__(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?)', (key, json.dumps(value)))
        self.db.commit()
    def __delitem__(self, key):
        if key not in self: raise KeyError(key)
        self.db.execute('DELETE FROM sessions WHERE id=?', (key,)); self.db.commit()
    def __iter__(self):
        return iter([row[0] for row in self.db.execute('SELECT id FROM sessions')])
    def __len__(self):
        return self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]

SESSIONS = {}
LOCK = threading.Lock()
ROOT = Path(__file__).resolve().parent.parent / 'web'

class APIError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)

class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip += 1
        if tag in ('br','p','div'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

def plain(value):
    p=Text(); p.feed(value); return ''.join(p.parts)

def node(ns, name, attrs=None, text=None):
    e=ET.Element('{'+ns+'}'+name, attrs or {})
    e.text=text
    return e

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class Zimbra:
    def __init__(self, url):
        u=urllib.parse.urlsplit(url)
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError('ZIMBRA_URL must be an HTTPS origin with a valid certificate')
        self.url=url.rstrip('/')+'/service/soap/'
        self.opener=urllib.request.build_opener(NoRedirect())
    def call(self, request, token=None):
        envelope=node(SOAP,'Envelope'); header=ET.SubElement(envelope,'{'+SOAP+'}Header')
        context=ET.SubElement(header,'{urn:zimbra}context')
        if token: ET.SubElement(context,'{urn:zimbra}authToken').text=token
        body=ET.SubElement(envelope,'{'+SOAP+'}Body'); body.append(request)
        req=urllib.request.Request(self.url, ET.tostring(envelope), {'Content-Type':'application/soap+xml; charset=utf-8'})
        try:
            with self.opener.open(req, timeout=25) as response:
                raw=response.read(8*1024*1024+1)
        except urllib.error.HTTPError as e:
            raw=e.read(65536)
        except (urllib.error.URLError, TimeoutError):
            raise APIError('Mail server is unavailable. Try again later.',502)
        if len(raw)>8*1024*1024 or b'<!DOCTYPE' in raw.upper():
            raise APIError('Invalid mail server response',502)
        try: doc=ET.fromstring(raw)
        except ET.ParseError: raise APIError('Invalid mail server response',502)
        fault=doc.find('.//{'+SOAP+'}Fault')
        if fault is not None:
            code=fault.find('.//{urn:zimbra}Code')
            auth=code is not None and code.text in ('account.AUTH_FAILED','service.AUTH_REQUIRED','service.AUTH_EXPIRED')
            raise APIError('Invalid or expired login' if auth else 'Mail server rejected this operation',401 if auth else 502)
        result=doc.find('{'+SOAP+'}Body')
        if result is None or not len(result): raise APIError('Empty mail server response',502)
        return result[0]
    def login(self, email, password):
        r=node(ACCOUNT,'AuthRequest'); r.append(node(ACCOUNT,'account',{'by':'name'},email)); r.append(node(ACCOUNT,'password',text=password))
        out=self.call(r); token=out.find('{'+ACCOUNT+'}authToken'); lifetime=out.find('{'+ACCOUNT+'}lifetime')
        if token is None or not token.text: raise APIError('Login failed',401)
        return token.text, min(int(lifetime.text)/1000 if lifetime is not None else 3600,3600)
    def folder_map(self, token):
        r=node(MAIL,'GetFolderRequest'); r.append(node(MAIL,'folder',{'l':'1'})); out=self.call(r,token)
        mapping=dict(FOLDERS)
        for f in out.iter('{'+MAIL+'}folder'):
            if f.get('name')=='Archive' and f.get('l')=='1': mapping['archive']=f.get('id')
        return mapping
    def messages(self, token):
        folders=self.folder_map(token); reverse={v:k for k,v in folders.items()}; result=[]; more=False
        r=node(MAIL,'SearchRequest',{'types':'message','limit':'50','sortBy':'dateDesc'})
        r.append(node(MAIL,'query',text='is:anywhere'))
        out=self.call(r,token); more=out.get('more')=='1'
        for summary in out.findall('{'+MAIL+'}m'):
            req=node(MAIL,'GetMsgRequest'); req.append(node(MAIL,'m',{'id':summary.get('id'),'read':'0'}))
            response=self.call(req,token); m=response.find('{'+MAIL+'}m')
            if m is None: continue
            addresses=m.findall('{'+MAIL+'}e'); sender=next((e for e in addresses if e.get('t')=='f'),None)
            bodies=[]
            for part in m.iter('{'+MAIL+'}mp'):
                content=part.find('{'+MAIL+'}content')
                if content is not None and part.get('ct') in ('text/plain','text/html') and not part.get('filename'):
                    bodies.append((part.get('ct'),content.text or ''))
            value=next((v for t,v in bodies if t=='text/plain'),None)
            if value is None: value=plain(next((v for t,v in bodies if t=='text/html'),''))
            flags=m.get('f',''); attachments=[{'name':p.get('filename'),'size':p.get('s','')} for p in m.iter('{'+MAIL+'}mp') if p.get('filename')]
            subject=m.find('{'+MAIL+'}su')
            result.append({'id':m.get('id'),'from':{'name':sender.get('p') or sender.get('a','') if sender is not None else '', 'email':sender.get('a','') if sender is not None else ''},'to':[e.get('a','') for e in addresses if e.get('t')=='t'],'cc':[e.get('a','') for e in addresses if e.get('t')=='c'],'subject':subject.text or '' if subject is not None else '', 'body':html.escape(value).replace('\n','<br>'),'folder':reverse.get(m.get('l'),'other'),'read':'u' not in flags,'starred':'f' in flags,'important':'+' in flags or '!' in flags,'date':int(m.get('d','0')),'labels':[],'hasAttachment':bool(attachments),'attachments':attachments})
        return {'emails':result,'more':more,'limit':50}
    def write_message(self, token, data, draft=False):
        if data.get('attachments'): raise APIError('Attachment upload is not implemented yet; remove attachments before sending or saving.')
        request=node(MAIL,'SaveDraftRequest' if draft else 'SendMsgRequest')
        m=node(MAIL,'m',{'id':str(data['id'])} if draft and data.get('id') else {})
        for kind in ('to','cc'):
            for address in re.split(r'[,;\n]+', str(data.get(kind,''))):
                address=address.strip()
                if not address: continue
                if not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+',address): raise APIError('Enter recipient email addresses without display names.')
                m.append(node(MAIL,'e',{'t':'t' if kind=='to' else 'c','a':address}))
        if not draft and not any(e.get('t')=='t' for e in m): raise APIError('Add a recipient')
        m.append(node(MAIL,'su',text=str(data.get('subject',''))))
        part=node(MAIL,'mp',{'ct':'text/plain'}); part.append(node(MAIL,'content',text=plain(str(data.get('body',''))))); m.append(part)
        request.append(m); out=self.call(request,token); message=out.find('{'+MAIL+'}m')
        return {'id':message.get('id') if message is not None else None}
    def action(self, token, data):
        ids=data.get('ids'); op=data.get('op')
        if not isinstance(ids,list) or not ids or len(ids)>50 or any(not re.fullmatch(r'\d+',str(i)) for i in ids): raise APIError('Invalid message selection')
        attrs={'id':','.join(map(str,ids))}
        if op=='move':
            folder=data.get('folder'); folders=self.folder_map(token)
            if folder=='archive' and folder not in folders:
                r=node(MAIL,'CreateFolderRequest'); r.append(node(MAIL,'folder',{'name':'Archive','l':'1','view':'message'}))
                out=self.call(r,token); folders[folder]=out.find('{'+MAIL+'}folder').get('id')
            if folder not in folders: raise APIError('Unknown folder')
            attrs.update(op='move',l=folders[folder])
        elif op in ('read','star','important'): attrs['op']=('' if data.get('value') else '!')+{'read':'read','star':'flag','important':'priority'}[op]
        elif op=='delete': attrs['op']='delete'
        else: raise APIError('Unsupported operation')
        r=node(MAIL,'MsgActionRequest'); r.append(node(MAIL,'action',attrs)); self.call(r,token)
        return {'ok':True}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def log_message(self, *args): pass  # Never log passwords, session IDs or message data.
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','same-origin')
        super().end_headers()
    def reply(self, status, data, cookie=None):
        raw=json.dumps(data).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)))
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(raw)
    def session(self):
        c=SimpleCookie(); c.load(self.headers.get('Cookie','')); sid=c.get('dejoiy_session'); sid=sid.value if sid else ''
        with LOCK:
            expired=[k for k,v in SESSIONS.items() if v['expires']<=time.time()]
            for k in expired: SESSIONS.pop(k,None)
            session=SESSIONS.get(sid)
        if not session: raise APIError('Sign in to your mailbox',401)
        return sid,session
    def do_GET(self):
        if self.path=='/js/runtime-config.js':
            raw=b'window.DEJOIY_LIVE=true;'; self.send_response(200); self.send_header('Content-Type','text/javascript'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw); return
        if self.path.startswith('/api/'):
            try:
                if self.path=='/api/config': return self.reply(200,{'mode':'zimbra','configured':bool(self.server.zimbra)})
                _,s=self.session()
                if self.path=='/api/session': return self.reply(200,{'user':s['user'],'csrf':s['csrf']})
                if self.path=='/api/mail': return self.reply(200,self.server.zimbra.messages(s['token']))
                raise APIError('Not found',404)
            except APIError as e: return self.reply(e.status,{'error':str(e)})
        super().do_GET()
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin != self.server.app_origin: raise APIError('Invalid request origin',403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise APIError('JSON required',415)
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024*1024: raise APIError('Request too large or empty',413)
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise APIError('JSON object required')
            if not self.server.zimbra: raise APIError('Set ZIMBRA_URL to connect a mail server',503)
            if self.path=='/api/login':
                with LOCK:
                    now=time.time(); attempts=self.server.attempts
                    for key in list(attempts):
                        attempts[key]=[t for t in attempts[key] if t>now-60]
                        if not attempts[key]: del attempts[key]
                    key=self.client_address[0]
                    if ipaddress.ip_address(key).is_loopback and self.headers.get('X-Real-IP'):
                        key=str(ipaddress.ip_address(self.headers['X-Real-IP']))
                    if len(attempts.get(key,[]))>=10: raise APIError('Too many login attempts; wait one minute',429)
                    attempts.setdefault(key,[]).append(now)
                email=str(data.get('email','')).strip(); password=str(data.get('password',''))
                if not email or len(email)>320 or not password or len(password)>4096: raise APIError('Enter an email and password')
                token,lifetime=self.server.zimbra.login(email,password)
                s={'token':token,'expires':time.time()+lifetime,'csrf':secrets.token_urlsafe(32),'user':{'email':email,'name':email.split('@')[0],'signature':''}}
                sid=secrets.token_urlsafe(32)
                with LOCK:
                    for key in list(SESSIONS):
                        if SESSIONS[key]['expires'] <= time.time(): del SESSIONS[key]
                    if len(SESSIONS)>=1000: raise APIError('Session capacity reached',503)
                    old=SimpleCookie(); old.load(self.headers.get('Cookie','')); oldsid=old.get('dejoiy_session')
                    if oldsid: SESSIONS.pop(oldsid.value,None)
                    SESSIONS[sid]=s
                secure='; Secure' if self.server.app_origin.startswith('https:') else ''
                return self.reply(200,{'user':s['user'],'csrf':s['csrf']},f'dejoiy_session={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age={int(lifetime)}'+secure)
            sid,s=self.session()
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): raise APIError('Invalid request token',403)
            if self.path=='/api/logout':
                with LOCK: SESSIONS.pop(sid,None)
                return self.reply(200,{'ok':True},'dejoiy_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
            if self.path=='/api/send': return self.reply(200,self.server.zimbra.write_message(s['token'],data))
            if self.path=='/api/draft': return self.reply(200,self.server.zimbra.write_message(s['token'],data,True))
            if self.path=='/api/action': return self.reply(200,self.server.zimbra.action(s['token'],data))
            raise APIError('Not found',404)
        except APIError as e: self.reply(e.status,{'error':str(e)})
        except (ValueError,TypeError): self.reply(400,{'error':'Invalid request'})
        except Exception: self.reply(502,{'error':'Mail operation failed. Try again later.'})

def serve():
    global SESSIONS
    if os.environ.get('SESSION_DB'):
        SESSIONS = SessionStore(os.environ['SESSION_DB'])
    port=int(os.environ.get('PORT','8080')); origin=os.environ.get('APP_ORIGIN',f'http://localhost:{port}')
    parsed=urllib.parse.urlsplit(origin)
    if parsed.scheme!='https' and parsed.hostname not in ('localhost','127.0.0.1'):
        raise ValueError('Public APP_ORIGIN must use HTTPS')
    server=ThreadingHTTPServer((os.environ.get('BIND','127.0.0.1'),port),Handler)
    server.app_origin=origin.rstrip('/'); server.attempts={}
    url=os.environ.get('ZIMBRA_URL'); server.zimbra=Zimbra(url) if url else None
    print(f'Dejoiy Mail: {origin}; backend '+('configured' if url else 'requires ZIMBRA_URL'))
    server.serve_forever()

if __name__=='__main__': serve()
