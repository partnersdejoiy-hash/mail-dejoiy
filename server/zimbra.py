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
import base64
import binascii
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
ADMIN = 'urn:zimbraAdmin'
FOLDERS = {'inbox':'2','sent':'5','drafts':'6','spam':'4','trash':'3'}
MAX_ATTACHMENT_BYTES=15*1024*1024
MAX_REQUEST_BYTES=22*1024*1024
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

class SafeHTML(HTMLParser):
    tags={'p','div','span','br','b','strong','i','em','u','s','strike','ul','ol','li','blockquote','pre','code','h1','h2','h3','a','table','tbody','thead','tr','td','th'}
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0; self.stack=[]
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','iframe','object','svg','math','head'):
            self.skip+=1; return
        if self.skip or tag not in self.tags: return
        safe=''
        if tag=='a':
            href=dict(attrs).get('href','').strip()
            if re.match(r'^(?:https?://|mailto:)',href,re.I):
                safe=' href="'+html.escape(href,quote=True)+'" target="_blank" rel="noopener noreferrer"'
        self.parts.append('<'+tag+safe+'>')
        if tag!='br': self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in ('script','style','iframe','object','svg','math','head'):
            self.skip=max(0,self.skip-1); return
        if not self.skip and tag in self.stack:
            while self.stack:
                last=self.stack.pop(); self.parts.append('</'+last+'>')
                if last==tag: break
    def handle_data(self, value):
        if not self.skip: self.parts.append(html.escape(value))

def safe_html(value):
    parser=SafeHTML(); parser.feed(value); parser.close()
    return ''.join(parser.parts)+''.join('</'+t+'>' for t in reversed(parser.stack))

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
        self.origin=url.rstrip('/')
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
            value=code.text if code is not None else ''
            auth=value in ('account.AUTH_FAILED','service.AUTH_REQUIRED','service.AUTH_EXPIRED')
            messages={
                'service.PERM_DENIED':'Your account does not have permission for this operation.',
                'account.ACCOUNT_EXISTS':'This mailbox already exists.',
                'account.DOMAIN_EXISTS':'This domain already exists.',
                'account.NO_SUCH_DOMAIN':'Add the mailbox domain before creating a user.',
                'account.INVALID_PASSWORD':'The password does not meet the mailbox password policy.',
                'mail.QUOTA_EXCEEDED':'Mailbox storage is full. Free space before sending.',
                'mail.SEND_ABORTED_ADDRESS_FAILURE':'The mail server rejected a recipient address. Check the recipients.',
                'mail.MESSAGE_TOO_BIG':'The message exceeds the mail server size limit.',
            }
            raise APIError('Invalid or expired login' if auth else messages.get(value,'Mail server rejected this operation'),401 if auth else 502)
        result=doc.find('{'+SOAP+'}Body')
        if result is None or not len(result): raise APIError('Empty mail server response',502)
        return result[0]
    def login(self, email, password):
        r=node(ACCOUNT,'AuthRequest'); r.append(node(ACCOUNT,'account',{'by':'name'},email)); r.append(node(ACCOUNT,'password',text=password))
        out=self.call(r); token=out.find('{'+ACCOUNT+'}authToken'); lifetime=out.find('{'+ACCOUNT+'}lifetime')
        if token is None or not token.text: raise APIError('Login failed',401)
        return token.text, min(int(lifetime.text)/1000 if lifetime is not None else 3600,3600)
    def capabilities(self, token):
        response=self.call(node(ACCOUNT,'GetInfoRequest',{'sections':'attrs'}),token)
        attrs={a.get('name') or a.get('n'):a.text or '' for a in response.findall('.//{'+ACCOUNT+'}attr')}
        global_admin=attrs.get('zimbraIsAdminAccount')=='TRUE'
        delegated=attrs.get('zimbraIsDelegatedAdminAccount')=='TRUE'
        return {'isAdmin':global_admin or delegated,'canManageRoles':global_admin}
    def folder_map(self, token):
        r=node(MAIL,'GetFolderRequest'); r.append(node(MAIL,'folder',{'l':'1'})); out=self.call(r,token)
        mapping=dict(FOLDERS)
        for f in out.iter('{'+MAIL+'}folder'):
            if f.get('name')=='Archive' and f.get('l')=='1': mapping['archive']=f.get('id')
        return mapping
    def messages(self, token, offset=0):
        folders=self.folder_map(token); reverse={v:k for k,v in folders.items()}; result=[]; more=False
        r=node(MAIL,'SearchRequest',{'types':'message','limit':'50','offset':str(offset),'sortBy':'dateDesc'})
        r.append(node(MAIL,'query',text='is:anywhere'))
        out=self.call(r,token); more=out.get('more')=='1'
        for summary in out.findall('{'+MAIL+'}m'):
            req=node(MAIL,'GetMsgRequest'); req.append(node(MAIL,'m',{'id':summary.get('id'),'read':'0','html':'1','neuter':'1'}))
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
            rich=next((v for t,v in bodies if t=='text/html'),None)
            display=safe_html(rich) if rich is not None else html.escape(value).replace('\n','<br>')
            flags=m.get('f',''); attachments=[{'name':p.get('filename'),'size':p.get('s',''),'mid':m.get('id'),'part':p.get('part')} for p in m.iter('{'+MAIL+'}mp') if p.get('filename')]
            subject=m.find('{'+MAIL+'}su')
            result.append({'id':m.get('id'),'conversationId':m.get('cid') or m.get('id'),'messageId':m.get('mid') or '', 'inReplyTo':m.get('irt') or '', 'from':{'name':sender.get('p') or sender.get('a','') if sender is not None else '', 'email':sender.get('a','') if sender is not None else ''},'to':[e.get('a','') for e in addresses if e.get('t')=='t'],'cc':[e.get('a','') for e in addresses if e.get('t')=='c'],'subject':subject.text or '' if subject is not None else '', 'body':display,'folder':reverse.get(m.get('l'),'other'),'read':'u' not in flags,'starred':'f' in flags,'important':'+' in flags or '!' in flags,'date':int(m.get('d','0')),'labels':[label for label in m.get('tn','').split(',') if label],'hasAttachment':bool(attachments),'attachments':attachments})
        return {'emails':result,'more':more,'limit':50,'offset':offset,'nextOffset':offset+len(out.findall('{'+MAIL+'}m'))}
    def write_message(self, token, data, draft=False):
        request=node(MAIL,'SaveDraftRequest' if draft else 'SendMsgRequest')
        attrs={}
        if data.get('id'):
            if not re.fullmatch(r'\d+',str(data['id'])): raise APIError('Invalid draft selection.')
            attrs['id' if draft else 'did']=str(data['id'])
        m=node(MAIL,'m',attrs)
        for kind in ('to','cc','bcc'):
            for address in re.split(r'[,;\n]+', str(data.get(kind,''))):
                address=address.strip()
                if not address: continue
                if not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+',address): raise APIError('Enter recipient email addresses without display names.')
                local,domain=address.rsplit('@',1)
                if domain.lower() in ('gmail.com','googlemail.com') and not re.fullmatch(r'[a-zA-Z0-9.]+(?:\+[^\s<>@]+)?',local):
                    raise APIError('Check the Gmail recipient address for a typo. Gmail usernames use letters, numbers and dots; +tags are supported.')
                m.append(node(MAIL,'e',{'t':{'to':'t','cc':'c','bcc':'b'}[kind],'a':address}))
        if not draft and not any(e.get('t')=='t' for e in m): raise APIError('Add a recipient')
        in_reply_to=data.get('inReplyTo')
        if in_reply_to:
            if not isinstance(in_reply_to,str) or len(in_reply_to)>998 or not re.fullmatch(r'<[^<>\s]+>',in_reply_to): raise APIError('Invalid reply reference.')
            m.set('irt',in_reply_to)
        m.append(node(MAIL,'su',text=str(data.get('subject',''))))
        body=str(data.get('body',''))
        alternative=node(MAIL,'mp',{'ct':'multipart/alternative'})
        part=node(MAIL,'mp',{'ct':'text/plain'}); part.append(node(MAIL,'content',text=plain(body))); alternative.append(part)
        part=node(MAIL,'mp',{'ct':'text/html'}); part.append(node(MAIL,'content',text=safe_html(body))); alternative.append(part)
        m.append(alternative)
        attachments=data.get('attachments',[])
        if not isinstance(attachments,list) or len(attachments)>20: raise APIError('Select up to 20 attachments.')
        uploads=[]; existing=[]; total=0
        for item in attachments:
            if not isinstance(item,dict): raise APIError('Invalid attachment.')
            if item.get('mid') and item.get('part'):
                if not re.fullmatch(r'\d+',str(item['mid'])) or not re.fullmatch(r'\d+(?:\.\d+)*',str(item['part'])):
                    raise APIError('Invalid attachment reference.')
                existing.append(item); continue
            try: raw=base64.b64decode(item.get('data',''),validate=True)
            except (ValueError,TypeError,binascii.Error): raise APIError('Invalid attachment data.')
            if 'data' not in item: raise APIError('Select the attachment file again.')
            total+=len(raw)
            if total>MAX_ATTACHMENT_BYTES: raise APIError('Attachments must total 15 MB or less.')
            name=str(item.get('name','attachment'))
            if not name or len(name)>255 or any(ord(c)<32 for c in name): raise APIError('Invalid attachment filename.')
            mime=str(item.get('type','application/octet-stream'))
            if not re.fullmatch(r'[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+',mime): mime='application/octet-stream'
            uploads.append((raw,name,mime))
        if uploads or existing:
            attach=node(MAIL,'attach')
            if uploads: attach.set('aid',','.join(self.upload(token,*item) for item in uploads))
            for item in existing: attach.append(node(MAIL,'mp',{'mid':str(item['mid']),'part':str(item['part'])}))
            m.append(attach)
        request.append(m); out=self.call(request,token); message=out.find('{'+MAIL+'}m')
        return {'id':message.get('id') if message is not None else None,'accepted':not draft,'draftRemoved':bool(not draft and data.get('id'))}
    def upload(self, token, raw, name, mime):
        filename=html.escape(name,quote=True).encode('ascii','xmlcharrefreplace').decode()
        request=urllib.request.Request(self.origin+'/service/upload?fmt=raw,extended',raw,
            {'Content-Type':mime,'Content-Disposition':'attachment; filename="'+filename+'"','Cookie':'ZM_AUTH_TOKEN='+token},method='POST')
        try:
            with self.opener.open(request,timeout=60) as response: value=response.read(65536).decode()
            status,_,payload=value.split(',',2)
            if status.strip()!='200': raise ValueError()
            items=json.loads(payload); aid=items[0]['aid']
            if not isinstance(aid,str) or not re.fullmatch(r'[a-zA-Z0-9:-]+',aid): raise ValueError()
            return aid
        except (urllib.error.URLError,TimeoutError,ValueError,KeyError,IndexError):
            raise APIError('Attachment upload failed. Your message has not been submitted.',502)
    def download(self, token, mid, part):
        if not re.fullmatch(r'\d+',mid) or not re.fullmatch(r'\d+(?:\.\d+)*',part): raise APIError('Invalid attachment selection.')
        request=urllib.request.Request(self.origin+'/service/home/~/?'+urllib.parse.urlencode({'id':mid,'part':part}),
            headers={'Cookie':'ZM_AUTH_TOKEN='+token})
        try:
            with self.opener.open(request,timeout=60) as response: raw=response.read(25*1024*1024+1)
        except (urllib.error.URLError,TimeoutError): raise APIError('Attachment is unavailable.',502)
        if len(raw)>25*1024*1024: raise APIError('Attachment exceeds the 25 MB download limit.',413)
        return raw
    def action(self, token, data):
        ids=data.get('ids'); op=data.get('op')
        if op=='empty_trash':
            r=node(MAIL,'FolderActionRequest');r.append(node(MAIL,'action',{'id':FOLDERS['trash'],'op':'empty','recursive':'1'}))
            self.call(r,token);return {'ok':True}
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
        elif op=='label':
            label=str(data.get('label','')).strip()
            if not label or len(label)>64 or ',' in label or any(ord(c)<32 for c in label): raise APIError('Enter a label of up to 64 characters without commas.')
            tags=self.call(node(MAIL,'GetTagRequest'),token)
            if not any(tag.get('name')==label for tag in tags.findall('{'+MAIL+'}tag')):
                r=node(MAIL,'CreateTagRequest');r.append(node(MAIL,'tag',{'name':label}));self.call(r,token)
            attrs.update(op='tag',tn=label)
        elif op=='delete': attrs['op']='delete'
        else: raise APIError('Unsupported operation')
        r=node(MAIL,'MsgActionRequest'); r.append(node(MAIL,'action',attrs)); self.call(r,token)
        return {'ok':True}
    def contacts(self, token):
        out=self.call(node(MAIL,'GetContactsRequest',{'l':'7','sortBy':'nameAsc'}),token)
        result=[]
        for contact in out.findall('{'+MAIL+'}cn'):
            attrs={a.get('n'):a.text or '' for a in contact.findall('{'+MAIL+'}a')}
            if attrs.get('type')=='group': continue
            result.append({'id':contact.get('id'),'name':attrs.get('fullName') or ' '.join(filter(None,[attrs.get('firstName'),attrs.get('lastName')])) or contact.get('fileAsStr') or attrs.get('email',''),
                'email':attrs.get('email',''),'phone':attrs.get('mobilePhone') or attrs.get('workPhone',''),'org':attrs.get('company',''),'presence':'off'})
        return {'contacts':result}
    def contact_action(self, token, data):
        ident=data.get('id')
        if ident and not re.fullmatch(r'\d+',str(ident)): raise APIError('Invalid contact selection.')
        if data.get('op')=='delete':
            if not ident: raise APIError('Select a contact.')
            r=node(MAIL,'ContactActionRequest');r.append(node(MAIL,'action',{'id':str(ident),'op':'delete'}))
            self.call(r,token);return {'ok':True}
        if data.get('op')!='save': raise APIError('Unsupported contact operation.')
        name=str(data.get('name','')).strip();email=str(data.get('email','')).strip()
        if not name or len(name)>200 or not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+',email): raise APIError('Enter a name and valid email address.')
        r=node(MAIL,'ModifyContactRequest' if ident else 'CreateContactRequest')
        contact=node(MAIL,'cn',{'id':str(ident)} if ident else {'l':'7'})
        for attr,value in [('fullName',name),('fileAs','8:'+name),('email',email),('mobilePhone',str(data.get('phone',''))),('company',str(data.get('org','')))]:
            if len(value)>1000: raise APIError('Contact field is too long.')
            contact.append(node(MAIL,'a',{'n':attr},value))
        r.append(contact);out=self.call(r,token);contact=out.find('{'+MAIL+'}cn')
        if contact is None: raise APIError('Contact save response is missing.',502)
        return {'id':contact.get('id'),'ok':True}
    def preferences(self, token):
        out=self.call(node(ACCOUNT,'GetPrefsRequest'),token)
        prefs={p.get('name'):p.text or '' for p in out.findall('{'+ACCOUNT+'}pref')}
        return {'name':prefs.get('zimbraPrefFromDisplay',''),'signature':prefs.get('zimbraPrefMailSignature',''),
            'vacation':{'on':prefs.get('zimbraPrefOutOfOfficeReplyEnabled')=='TRUE','message':prefs.get('zimbraPrefOutOfOfficeReply',''),'subject':'Automatic reply'}}
    def save_preferences(self, token, data):
        r=node(ACCOUNT,'ModifyPrefsRequest')
        if data.get('op')=='profile':
            name=str(data.get('name','')).strip();signature=str(data.get('signature',''))
            if not name or len(name)>256 or len(signature)>8192: raise APIError('Enter a name and signature within the mailbox limits.')
            values={'zimbraPrefFromDisplay':name,'zimbraPrefMailSignature':signature}
        elif data.get('op')=='vacation':
            message=str(data.get('message',''))
            if len(message)>8192: raise APIError('Vacation reply must be at most 8192 characters.')
            if not isinstance(data.get('on'),bool): raise APIError('Invalid vacation responder setting.')
            values={'zimbraPrefOutOfOfficeReplyEnabled':'TRUE' if data['on'] else 'FALSE','zimbraPrefOutOfOfficeReply':message}
        else: raise APIError('Unsupported account setting.')
        for key,value in values.items():r.append(node(ACCOUNT,'pref',{'name':key},value))
        self.call(r,token);return {'ok':True}

class Admin(Zimbra):
    """Separate, upstream-authorized admin session; no shared service credentials."""
    def __init__(self, url):
        super().__init__(url)
        self.url=url.rstrip('/')+'/service/admin/soap/'
    def login(self, email, password):
        r=node(ADMIN,'AuthRequest')
        r.append(node(ADMIN,'account',{'by':'name'},email))
        r.append(node(ADMIN,'password',text=password))
        out=self.call(r)
        token=out.find('{'+ADMIN+'}authToken'); lifetime=out.find('{'+ADMIN+'}lifetime')
        if token is None or not token.text: raise APIError('Administrator sign-in failed.',403)
        return token.text,min(int(lifetime.text)/1000 if lifetime is not None else 900,900)
    def overview(self, token):
        users=self.call(node(ADMIN,'GetAllAccountsRequest'),token)
        domains=self.call(node(ADMIN,'GetAllDomainsRequest'),token)
        def attributes(element):
            return {a.get('n'):a.text or '' for a in element.findall('{'+ADMIN+'}a')}
        accounts=[]
        for account in users.findall('{'+ADMIN+'}account'):
            a=attributes(account)
            if a.get('zimbraIsSystemResource')=='TRUE': continue
            accounts.append({'id':account.get('id'),'email':account.get('name'),
                'name':a.get('displayName') or account.get('name'),
                'status':a.get('zimbraAccountStatus','active'),
                'role':'Admin' if a.get('zimbraIsAdminAccount')=='TRUE' else 'Delegated Admin' if a.get('zimbraIsDelegatedAdminAccount')=='TRUE' else 'User',
                'aliases':[v.text for v in account.findall('{'+ADMIN+'}a') if v.get('n')=='zimbraMailAlias' and v.text],
                'quota':a.get('zimbraMailQuota','0')})
        return {'users':accounts,'domains':[{'id':d.get('id'),'domain':d.get('name'),
            'status':attributes(d).get('zimbraDomainStatus','active')}
            for d in domains.findall('{'+ADMIN+'}domain')]}
    def action(self, token, data, actor):
        op=data.get('op')
        def require_global_admin():
            request=node(ADMIN,'GetAccountRequest')
            request.append(node(ADMIN,'account',{'by':'name'},actor))
            response=self.call(request,token)
            account=response.find('{'+ADMIN+'}account')
            if account is None or not any(a.get('n')=='zimbraIsAdminAccount' and a.text=='TRUE' for a in account.findall('{'+ADMIN+'}a')):
                raise APIError('Only a full administrator can assign administrator roles.',403)
        def account_role():
            role=data.get('role','User')
            if role not in ('User','Admin'): raise APIError('Select a valid mailbox role.')
            return role
        def password():
            value=data.get('password')
            if not isinstance(value,str) or not 1<=len(value)<=4096:
                raise APIError('Enter a password; mailbox password policies also apply.')
            return value
        if op=='create_user':
            email=str(data.get('email','')).strip().lower()
            if not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+',email) or len(email)>320:
                raise APIError('Enter a valid mailbox email address.')
            role=account_role()
            if role=='Admin': require_global_admin()
            r=node(ADMIN,'CreateAccountRequest')
            r.append(node(ADMIN,'name',text=email)); r.append(node(ADMIN,'password',text=password()))
            name=str(data.get('name','')).strip()
            if not name or len(name)>200: raise APIError('Enter a display name of up to 200 characters.')
            r.append(node(ADMIN,'a',{'n':'displayName'},name))
            r.append(node(ADMIN,'a',{'n':'zimbraIsAdminAccount'},'TRUE' if role=='Admin' else 'FALSE'))
        elif op=='create_domain':
            name=str(data.get('domain','')).strip().lower()
            if len(name)>253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',name):
                raise APIError('Enter a valid domain name.')
            r=node(ADMIN,'CreateDomainRequest'); r.append(node(ADMIN,'name',text=name))
        elif op in ('status','password','role','quota','add_alias','remove_alias'):
            ident=str(data.get('id',''))
            if not re.fullmatch(r'[a-fA-F0-9-]{36}',ident): raise APIError('Invalid mailbox selection.')
            lookup=node(ADMIN,'GetAccountRequest')
            lookup.append(node(ADMIN,'account',{'by':'id'},ident))
            out=self.call(lookup,token); account=out.find('{'+ADMIN+'}account')
            if account is None: raise APIError('Mailbox not found.',404)
            if op=='status':
                status=data.get('status')
                if status not in ('active','locked','maintenance'): raise APIError('Invalid mailbox status.')
                if account.get('name','').lower()==actor.lower() and status!='active':
                    raise APIError('You cannot lock your own administrator mailbox.')
                r=node(ADMIN,'ModifyAccountRequest'); r.append(node(ADMIN,'id',text=ident))
                r.append(node(ADMIN,'a',{'n':'zimbraAccountStatus'},status))
            elif op=='role':
                role=account_role()
                if account.get('name','').lower()==actor.lower(): raise APIError('You cannot change your own administrator role.')
                require_global_admin()
                r=node(ADMIN,'ModifyAccountRequest');r.append(node(ADMIN,'id',text=ident))
                r.append(node(ADMIN,'a',{'n':'zimbraIsAdminAccount'},'TRUE' if role=='Admin' else 'FALSE'))
                r.append(node(ADMIN,'a',{'n':'zimbraIsDelegatedAdminAccount'},'FALSE'))
            elif op=='quota':
                quota=data.get('quotaMB')
                if isinstance(quota,bool) or not isinstance(quota,int) or not 0<=quota<=10485760: raise APIError('Quota must be a whole number from 0 to 10485760 MB; 0 means unlimited.')
                r=node(ADMIN,'ModifyAccountRequest');r.append(node(ADMIN,'id',text=ident))
                r.append(node(ADMIN,'a',{'n':'zimbraMailQuota'},str(quota*1024*1024)))
            elif op in ('add_alias','remove_alias'):
                alias=str(data.get('alias','')).strip().lower()
                if len(alias)>320 or not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+',alias): raise APIError('Enter a valid alias email address.')
                r=node(ADMIN,'AddAccountAliasRequest' if op=='add_alias' else 'RemoveAccountAliasRequest')
                r.append(node(ADMIN,'id',text=ident));r.append(node(ADMIN,'alias',text=alias))
            else:
                r=node(ADMIN,'SetPasswordRequest'); r.append(node(ADMIN,'id',text=ident))
                r.append(node(ADMIN,'newPassword',text=password()))
        else: raise APIError('Unsupported administration operation.')
        self.call(r,token)
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
                if self.path=='/api/config': return self.reply(200,{'mode':'live','configured':bool(self.server.zimbra)})
                _,s=self.session()
                if self.path=='/api/session':
                    capabilities=self.server.zimbra.capabilities(s['token'])
                    return self.reply(200,{'user':{**s['user'],**capabilities},'csrf':s['csrf']})
                if self.path=='/api/mail': return self.reply(200,self.server.zimbra.messages(s['token']))
                if self.path=='/api/contacts': return self.reply(200,self.server.zimbra.contacts(s['token']))
                if self.path=='/api/preferences': return self.reply(200,self.server.zimbra.preferences(s['token']))
                if self.path.startswith('/api/mail?'):
                    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    try: offset=int(query.get('offset',['0'])[0])
                    except ValueError: raise APIError('Invalid mailbox page.')
                    if not 0<=offset<=1000000: raise APIError('Invalid mailbox page.')
                    return self.reply(200,self.server.zimbra.messages(s['token'],offset))
                if self.path.startswith('/api/attachment?'):
                    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    raw=self.server.zimbra.download(s['token'],query.get('mid',[''])[0],query.get('part',[''])[0])
                    name=query.get('name',['attachment'])[0]
                    self.send_response(200); self.send_header('Content-Type','application/octet-stream')
                    self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(name,safe=''))
                    self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw)))
                    self.end_headers(); self.wfile.write(raw); return
                if self.path=='/api/admin':
                    client,token=self.admin_session(s)
                    return self.reply(200,client.overview(token))
                raise APIError('Not found',404)
            except APIError as e: return self.reply(e.status,{'error':str(e)})
            except (ValueError,TypeError): return self.reply(400,{'error':'Invalid request'})
            except Exception: return self.reply(502,{'error':'Mail operation failed. Try again later.'})
        if self.path=='/admin/':
            self.send_response(302); self.send_header('Location','/admin'); self.end_headers(); return
        if self.path=='/admin':
            self.path='/index.html'
        super().do_GET()
    def admin_session(self, session):
        client=getattr(self.server,'admin',None)
        if not client: raise APIError('Mail administration is not configured on this server.',503)
        if not session.get('admin_token') or session.get('admin_expires',0)<=time.time():
            raise APIError('Sign in to Dejoiy Mail Admin to continue.',403)
        return client,session['admin_token']
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin != self.server.app_origin: raise APIError('Invalid request origin',403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise APIError('JSON required',415)
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_REQUEST_BYTES: raise APIError('Request too large or empty',413)
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise APIError('JSON object required')
            if not self.server.zimbra: raise APIError('Mail server setup is pending. Contact your administrator.',503)
            if self.path in ('/api/login','/api/admin/login'):
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
            if self.path=='/api/login':
                email=str(data.get('email','')).strip(); password=str(data.get('password',''))
                if not email or len(email)>320 or not password or len(password)>4096: raise APIError('Enter an email and password')
                token,lifetime=self.server.zimbra.login(email,password)
                s={'token':token,'expires':time.time()+lifetime,'csrf':secrets.token_urlsafe(32),'user':{'email':email,'name':email.split('@')[0],'signature':''}}
                s['user'].update(self.server.zimbra.capabilities(token))
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
            if self.path=='/api/admin/login':
                client=getattr(self.server,'admin',None)
                if not client: raise APIError('Mail administration is not configured on this server.',503)
                password=str(data.get('password',''))
                if not password or len(password)>4096: raise APIError('Enter your administrator password.')
                token,lifetime=client.login(s['user']['email'],password)
                with LOCK:
                    if sid not in SESSIONS: raise APIError('Sign in to your mailbox',401)
                    s.update(admin_token=token,admin_expires=time.time()+min(lifetime,900))
                    SESSIONS[sid]=s
                return self.reply(200,{'ok':True})
            if self.path=='/api/admin/logout':
                with LOCK:
                    s.pop('admin_token',None); s.pop('admin_expires',None)
                    SESSIONS[sid]=s
                return self.reply(200,{'ok':True})
            if self.path=='/api/admin/action':
                client,token=self.admin_session(s)
                return self.reply(200,client.action(token,data,s['user']['email']))
            if self.path=='/api/send': return self.reply(200,self.server.zimbra.write_message(s['token'],data))
            if self.path=='/api/draft': return self.reply(200,self.server.zimbra.write_message(s['token'],data,True))
            if self.path=='/api/action': return self.reply(200,self.server.zimbra.action(s['token'],data))
            if self.path=='/api/contacts': return self.reply(200,self.server.zimbra.contact_action(s['token'],data))
            if self.path=='/api/preferences': return self.reply(200,self.server.zimbra.save_preferences(s['token'],data))
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
    admin_url=os.environ.get('ZIMBRA_ADMIN_URL'); server.admin=Admin(admin_url) if admin_url else None
    print(f'Dejoiy Mail: {origin}; backend '+('configured' if url else 'requires ZIMBRA_URL'))
    server.serve_forever()

if __name__=='__main__': serve()
