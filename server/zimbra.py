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

THEME_ID = re.compile(r'[a-z0-9]{1,40}')
DATA_IMAGE = re.compile(r'data:image/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/]+={0,2}')
MAX_CUSTOM_BACKGROUND = 4*1024*1024
GLASS_MAX = 85
def clean_appearance(data):
    """Only the known appearance fields, each bounded, survive to storage."""
    out={}
    theme=data.get('theme')
    if not isinstance(theme,str) or not THEME_ID.fullmatch(theme): raise APIError('Invalid theme.')
    out['theme']=theme
    if data.get('brightness') not in ('light','medium','dark'): raise APIError('Invalid brightness.')
    out['brightness']=data['brightness']
    glass=data.get('glass',{})
    if not isinstance(glass,dict) or len(glass)>100: raise APIError('Invalid transparency settings.')
    for key,value in glass.items():
        if not isinstance(key,str) or not THEME_ID.fullmatch(key) or isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=GLASS_MAX: raise APIError('Invalid transparency settings.')
    out['glass']=glass
    custom=data.get('customBg','')
    if not isinstance(custom,str) or len(custom)>MAX_CUSTOM_BACKGROUND or (custom and not DATA_IMAGE.fullmatch(custom)): raise APIError('Background photo must be a PNG, JPEG, WebP or GIF under 3 MB.')
    out['customBg']=custom
    return out

class AppearanceStore:
    """Per-mailbox appearance, keyed by the upstream account id so it follows the user across devices."""
    def __init__(self, path=None, table='appearance'):
        self.lock=threading.Lock(); self.memory={}; self.db=None; self.table=table
        if path:
            self.db=sqlite3.connect(path, check_same_thread=False, timeout=10); os.chmod(path, 0o600)
            self.db.execute(f'CREATE TABLE IF NOT EXISTS {table} (account TEXT PRIMARY KEY, data TEXT NOT NULL)'); self.db.commit()
    def get(self, account):
        with self.lock:
            if self.db is None: return dict(self.memory.get(account,{}))
            row=self.db.execute(f'SELECT data FROM {self.table} WHERE account=?',(account,)).fetchone()
            return json.loads(row[0]) if row else {}
    def put(self, account, data):
        with self.lock:
            if self.db is None: self.memory[account]=dict(data); return
            self.db.execute(f'INSERT OR REPLACE INTO {self.table} VALUES (?, ?)',(account,json.dumps(data))); self.db.commit()

IMAGE_MAGIC = {'png':lambda b:b.startswith(b'\x89PNG\r\n\x1a\n'),'jpeg':lambda b:b.startswith(b'\xff\xd8\xff'),
    'gif':lambda b:b[:6] in (b'GIF87a',b'GIF89a'),'webp':lambda b:b[:4]==b'RIFF' and b[8:12]==b'WEBP'}
IMAGE_EXT = {'png':'png','jpeg':'jpg','gif':'gif','webp':'webp'}
IMAGE_MIME = {'png':'image/png','jpg':'image/jpeg','gif':'image/gif','webp':'image/webp'}
def decode_image(value, kinds, limit, what):
    """A data: URL whose bytes really are one of the allowed raster formats (never SVG)."""
    match=re.fullmatch(r'data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/]+={0,2})',value) if isinstance(value,str) and len(value)<=limit*4//3+64 else None
    if not match or match.group(1) not in kinds: raise APIError(f'{what} must be a {", ".join(k.upper() for k in kinds)} image.')
    raw=base64.b64decode(match.group(2))
    if len(raw)>limit: raise APIError(f'{what} must be under {limit//1024} KB.')
    if not IMAGE_MAGIC[match.group(1)](raw): raise APIError(f'{what} is not a valid image file.')
    return IMAGE_EXT[match.group(1)],raw

MAX_AVATAR_BYTES = 300*1024
class AvatarStore:
    """Profile photos keyed by mailbox address; colleagues on the same domain can see each other's."""
    def __init__(self, path=None):
        self.lock=threading.Lock(); self.memory={}; self.db=None
        if path:
            self.db=sqlite3.connect(path, check_same_thread=False); os.chmod(path, 0o600)
            self.db.execute('CREATE TABLE IF NOT EXISTS avatars (email TEXT PRIMARY KEY, domain TEXT NOT NULL, ext TEXT NOT NULL, data BLOB NOT NULL, version INTEGER NOT NULL)')
            self.db.execute('CREATE INDEX IF NOT EXISTS avatars_domain ON avatars(domain)'); self.db.commit()
    def put(self, email, ext, raw):
        email=email.lower(); row=(email,email.rsplit('@',1)[1],ext,raw,int(time.time()*1000))
        with self.lock:
            if self.db is None: self.memory[email]=row; return row[4]
            self.db.execute('INSERT OR REPLACE INTO avatars VALUES (?,?,?,?,?)',row); self.db.commit(); return row[4]
    def delete(self, email):
        with self.lock:
            if self.db is None: self.memory.pop(email.lower(),None); return
            self.db.execute('DELETE FROM avatars WHERE email=?',(email.lower(),)); self.db.commit()
    def get(self, email):
        with self.lock:
            if self.db is None: row=self.memory.get(email.lower()); return (row[2],row[3]) if row else None
            row=self.db.execute('SELECT ext,data FROM avatars WHERE email=?',(email.lower(),)).fetchone()
            return (row[0],bytes(row[1])) if row else None
    def versions(self, domain):
        with self.lock:
            if self.db is None: return {r[0]:r[4] for r in self.memory.values() if r[1]==domain}
            return {email:version for email,version in self.db.execute('SELECT email,version FROM avatars WHERE domain=?',(domain,))}

MAX_SIGNATURE_IMAGE_BYTES = 512*1024
MEDIA_NAME = re.compile(r'([a-f0-9]{32})\.(png|jpg|gif)')
class MediaStore:
    """Signature images. They are fetched by recipients' mail apps, so they are public under an
    unguessable name, like the image links any mail provider hands out."""
    def __init__(self, directory=None, per_account=100):
        self.lock=threading.Lock(); self.memory={}; self.owners={}; self.dir=Path(directory) if directory else None; self.per_account=per_account
        if self.dir: self.dir.mkdir(mode=0o700,exist_ok=True)
    def save(self, account, ext, raw):
        with self.lock:
            owned=self.owners.setdefault(account,self._count(account))
            if owned>=self.per_account: raise APIError('Signature image limit reached for this mailbox.',429)
            name=secrets.token_hex(16)+'.'+ext
            if self.dir:
                (self.dir/(name+'.owner')).write_text(account); (self.dir/name).write_bytes(raw)
            else: self.memory[name]=raw
            self.owners[account]=owned+1
            return name
    def _count(self, account):
        if not self.dir: return 0
        return sum(1 for f in self.dir.glob('*.owner') if f.read_text()==account)
    def get(self, name):
        if not MEDIA_NAME.fullmatch(name): return None
        if not self.dir: return self.memory.get(name)
        path=self.dir/name
        return path.read_bytes() if path.is_file() else None

ADMIN_ASSETS = {'/admin.html','/js/admin-app.js','/css/admin.css'}
DOMAIN_NAME = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')
LOCAL_PART = re.compile(r'[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?')
FREE_MAIL = {'gmail.com','googlemail.com','yahoo.com','yahoo.co.in','outlook.com','hotmail.com','live.com','msn.com','icloud.com','me.com',
    'aol.com','proton.me','protonmail.com','zoho.com','zohomail.in','yandex.com','gmx.com','mail.com','rediffmail.com'}
SIGNUP_TTL = 7*24*3600

def dns_lookup(name, kind='TXT'):
    """Public DNS answers via DNS-over-HTTPS, so checks match what the internet sees."""
    code={'TXT':16,'MX':15}[kind]
    for url in ('https://cloudflare-dns.com/dns-query','https://dns.google/resolve'):
        try:
            request=urllib.request.Request(url+'?'+urllib.parse.urlencode({'name':name,'type':kind}),headers={'Accept':'application/dns-json'})
            with urllib.request.urlopen(request,timeout=6) as response: answer=json.loads(response.read(262144))
        except (OSError,ValueError): continue
        found=[a.get('data','') for a in answer.get('Answer',[]) if a.get('type')==code]
        if kind=='TXT': return [''.join(re.findall(r'"((?:[^"\\]|\\.)*)"',d)) or d for d in found]
        return [d.split()[-1].rstrip('.').lower() for d in found if d.split()]
    raise APIError('DNS could not be checked right now. Try again in a minute.',502)

def txt_records(domain): return dns_lookup(domain,'TXT')

def domain_records(domain, mail_host, dkim_dir):
    """The DNS records a hosted domain needs, each marked published or not in public DNS."""
    dkim=None
    if dkim_dir:
        try: dkim=json.loads((Path(dkim_dir)/(domain+'.json')).read_text())
        except (OSError,ValueError): dkim=None
    txt=dns_lookup(domain); mx=dns_lookup(domain,'MX')
    records=[{'kind':'MX','type':'MX','host':'@','value':mail_host,'priority':10,'ok':mail_host in mx},
        {'kind':'SPF','type':'TXT','host':'@','value':f'v=spf1 mx a:{mail_host} ~all','ok':any(t.startswith('v=spf1') and (mail_host in t or ' mx' in t) for t in txt)}]
    if dkim: records.append({'kind':'DKIM','type':'TXT','host':dkim['host'],'value':dkim['value'],'ok':dkim['value'].replace(' ','') in [t.replace(' ','') for t in dns_lookup(dkim['host']+'.'+domain)]})
    else: records.append({'kind':'DKIM','type':'TXT','host':'','value':'','ok':False,'pending':True})
    records.append({'kind':'DMARC','type':'TXT','host':'_dmarc','value':f'v=DMARC1; p=quarantine; rua=mailto:postmaster@{domain}','ok':any(t.startswith('v=DMARC1') for t in dns_lookup('_dmarc.'+domain))})
    return records

class SignupStore:
    """Pending company sign-ups waiting for DNS proof. No passwords are ever stored here."""
    def __init__(self, path=None):
        self.lock=threading.Lock(); self.memory={}; self.db=None
        if path:
            self.db=sqlite3.connect(path, check_same_thread=False); os.chmod(path, 0o600)
            self.db.execute('CREATE TABLE IF NOT EXISTS signups (token TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL)'); self.db.commit()
    def _purge(self):
        cutoff=time.time()-SIGNUP_TTL
        if self.db is None: self.memory={k:v for k,v in self.memory.items() if v[1]>cutoff}
        else: self.db.execute('DELETE FROM signups WHERE created<?',(cutoff,)); self.db.commit()
    def put(self, token, data):
        with self.lock:
            self._purge()
            if (len(self.memory) if self.db is None else self.db.execute('SELECT COUNT(*) FROM signups').fetchone()[0])>=1000: raise APIError('Too many pending sign-ups. Try again later.',503)
            if self.db is None: self.memory[token]=(dict(data),time.time())
            else: self.db.execute('INSERT INTO signups VALUES (?,?,?)',(token,json.dumps(data),time.time())); self.db.commit()
    def get(self, token):
        with self.lock:
            self._purge()
            if self.db is None: return dict(self.memory[token][0]) if token in self.memory else None
            row=self.db.execute('SELECT data FROM signups WHERE token=?',(token,)).fetchone()
            return json.loads(row[0]) if row else None
    def delete(self, token):
        with self.lock:
            if self.db is None: self.memory.pop(token,None)
            else: self.db.execute('DELETE FROM signups WHERE token=?',(token,)); self.db.commit()

class Provisioner:
    """Creates a company's domain and first administrator with a dedicated service admin account."""
    def __init__(self, admin, email, password):
        self.admin=admin; self.email=email; self.password=password; self.cached=('',0)
    def token(self):
        if self.cached[1]>time.time()+60: return self.cached[0]
        token,lifetime=self.admin.login(self.email,self.password); self.cached=(token,time.time()+lifetime); return token
    def domain_exists(self, domain):
        request=node(ADMIN,'GetDomainRequest'); request.append(node(ADMIN,'domain',{'by':'name'},domain))
        try: self.admin.call(request,self.token()); return True
        except APIError as e:
            if e.code=='account.NO_SUCH_DOMAIN': return False
            raise
    def provision(self, domain, company, email, name, password):
        token=self.token(); created=[]
        try:
            r=node(ADMIN,'CreateDomainRequest'); r.append(node(ADMIN,'name',text=domain)); r.append(node(ADMIN,'a',{'n':'description'},company))
            created.append(('DeleteDomainRequest',self.admin.call(r,token).find('{'+ADMIN+'}domain').get('id')))
            r=node(ADMIN,'CreateAccountRequest'); r.append(node(ADMIN,'name',text=email)); r.append(node(ADMIN,'password',text=password))
            r.append(node(ADMIN,'a',{'n':'displayName'},name)); r.append(node(ADMIN,'a',{'n':'zimbraIsDelegatedAdminAccount'},'TRUE'))
            created.append(('DeleteAccountRequest',self.admin.call(r,token).find('{'+ADMIN+'}account').get('id')))
            r=node(ADMIN,'GrantRightRequest')
            r.append(node(ADMIN,'target',{'type':'domain','by':'name'},domain)); r.append(node(ADMIN,'grantee',{'type':'usr','by':'name'},email))
            r.append(node(ADMIN,'right',{'canDelegate':'1'},'domainAdminRights')); self.admin.call(r,token)
        except (APIError,AttributeError) as error:
            for request,ident in reversed(created):  # leave nothing half-created behind
                try: self.admin.call(node(ADMIN,request,{'id':ident}),token)
                except APIError: pass
            if isinstance(error,APIError) and error.code=='account.INVALID_PASSWORD': raise APIError('The password does not meet the mailbox password policy.')
            raise APIError('Your company mail could not be created. Nothing was changed; try again.',502)
SESSIONS = {}
LOCK = threading.Lock()
ROOT = Path(__file__).resolve().parent.parent / 'web'

class APIError(Exception):
    def __init__(self, message, status=400, code=''):
        self.status = status
        self.code = code  # upstream fault code, never shown to users
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
    def __init__(self, images=None):
        super().__init__(); self.parts=[]; self.skip=0; self.stack=[]; self.images=images
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','iframe','object','svg','math','head'):
            self.skip+=1; return
        if self.skip: return
        if tag=='img': return self.image(dict(attrs))
        if tag not in self.tags: return
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
    def image(self, attrs):
        # Zimbra's neutered copies keep the address in dfsrc; images are dropped unless the caller allows that address.
        src=(attrs.get('src') or attrs.get('dfsrc') or '').strip()
        if not self.images or not self.images(src): return
        safe=' src="'+html.escape(src,quote=True)+'"'
        for name in ('width','height'):
            value=(attrs.get(name) or '').strip()
            if re.fullmatch(r'\d{1,4}',value): safe+=f' {name}="{value}"'
        self.parts.append('<img'+safe+' alt="'+html.escape(attrs.get('alt') or '',quote=True)+'">')

def safe_html(value, images=None):
    parser=SafeHTML(images); parser.feed(value); parser.close()
    return ''.join(parser.parts)+''.join('</'+t+'>' for t in reversed(parser.stack))

def web_image(src):
    """Images a sender deliberately put in their own message: plain https links only."""
    return bool(re.fullmatch(r'https://[^\s"\'<>\\]{1,2000}',src))

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
                'account.DISTRIBUTION_LIST_EXISTS':'A mailing list or mailbox with this address already exists.',
                'account.NO_SUCH_ACCOUNT':'Mailbox not found.',
                'account.NO_SUCH_DISTRIBUTION_LIST':'Mailing list not found.',
                'account.NO_SUCH_COS':'Plan not found.',
                'account.DOMAIN_NOT_EMPTY':'Remove the mailboxes in this domain first.',
            }
            raise APIError('Invalid or expired login' if auth else messages.get(value,'Mail server rejected this operation'),401 if auth else 502,value)
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
    def account_id(self, token):
        account=self.call(node(ACCOUNT,'GetInfoRequest',{'sections':'mbox'}),token).find('{'+ACCOUNT+'}id')
        return account.text if account is not None and account.text else ''
    def folder_map(self, token):
        r=node(MAIL,'GetFolderRequest'); r.append(node(MAIL,'folder',{'l':'1'})); out=self.call(r,token)
        mapping=dict(FOLDERS)
        for f in out.iter('{'+MAIL+'}folder'):
            if f.get('name')=='Archive' and f.get('l')=='1': mapping['archive']=f.get('id')
        return mapping
    media_prefix=''  # public address of signature images, set when the server starts
    def own_image(self, src):
        # Only our own hosted signature images are shown; other remote images could track the reader.
        return bool(self.media_prefix) and src.startswith(self.media_prefix) and bool(MEDIA_NAME.fullmatch(src[len(self.media_prefix):]))
    def messages(self, token, offset=0):
        folders=self.folder_map(token); reverse={v:k for k,v in folders.items()}; result=[]; more=False
        # "Always display external images" lets plain https images through; otherwise only our own hosted ones show.
        prefs=node(ACCOUNT,'GetPrefsRequest'); prefs.append(node(ACCOUNT,'pref',{'name':'zimbraPrefDisplayExternalImages'}))
        external=any(p.text=='TRUE' for p in self.call(prefs,token).findall('{'+ACCOUNT+'}pref'))
        images=(lambda src: self.own_image(src) or web_image(src)) if external else self.own_image
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
            display=safe_html(rich,images) if rich is not None else html.escape(value).replace('\n','<br>')
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
        original=data.get('origId')
        if original:
            # Linking the original message keeps the reply in the same upstream conversation.
            if not isinstance(original,str) or not re.fullmatch(r'\d{1,12}',original): raise APIError('Invalid original message reference.')
            if data.get('replyType') not in ('r','w'): raise APIError('Invalid reply type.')
            m.set('origid',original); m.set('rt',data['replyType'])
        m.append(node(MAIL,'su',text=str(data.get('subject',''))))
        body=str(data.get('body',''))
        alternative=node(MAIL,'mp',{'ct':'multipart/alternative'})
        part=node(MAIL,'mp',{'ct':'text/plain'}); part.append(node(MAIL,'content',text=plain(body))); alternative.append(part)
        part=node(MAIL,'mp',{'ct':'text/html'}); part.append(node(MAIL,'content',text=safe_html(body,web_image))); alternative.append(part)
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
            'signatureHtml':safe_html(prefs.get('zimbraPrefMailSignatureHTML',''),web_image),
            'vacation':{'on':prefs.get('zimbraPrefOutOfOfficeReplyEnabled')=='TRUE','message':prefs.get('zimbraPrefOutOfOfficeReply',''),'subject':'Automatic reply'}}
    def save_preferences(self, token, data):
        r=node(ACCOUNT,'ModifyPrefsRequest')
        if data.get('op')=='profile':
            name=str(data.get('name','')).strip();signature=str(data.get('signature',''))
            if not name or len(name)>256 or len(signature)>8192: raise APIError('Enter a name and signature within the mailbox limits.')
            values={'zimbraPrefFromDisplay':name,'zimbraPrefMailSignature':signature}
            if 'signatureHtml' in data:
                rich=data['signatureHtml']
                if not isinstance(rich,str) or len(rich)>8192: raise APIError('Signature must be at most 8192 characters.')
                rich=safe_html(rich,web_image)
                if len(rich)>8192: raise APIError('Signature must be at most 8192 characters.')
                # The plain copy is what text-only mail apps show, so it follows the formatted one.
                values.update(zimbraPrefMailSignatureHTML=rich,zimbraPrefMailSignature=plain(rich).strip() if rich.strip() else '')
        elif data.get('op')=='vacation':
            message=str(data.get('message',''))
            if len(message)>8192: raise APIError('Vacation reply must be at most 8192 characters.')
            if not isinstance(data.get('on'),bool): raise APIError('Invalid vacation responder setting.')
            values={'zimbraPrefOutOfOfficeReplyEnabled':'TRUE' if data['on'] else 'FALSE','zimbraPrefOutOfOfficeReply':message}
        else: raise APIError('Unsupported account setting.')
        for key,value in values.items():r.append(node(ACCOUNT,'pref',{'name':key},value))
        self.call(r,token);return {'ok':True}
    # ---------- mailbox settings ----------
    # Each setting the web app offers maps onto a real mailbox preference, so it follows the
    # user to every device and to other mail apps. Only these keys can be written.
    def account_settings(self, token):
        out=self.call(node(ACCOUNT,'GetPrefsRequest'),token)
        prefs={p.get('name'):p.text or '' for p in out.findall('{'+ACCOUNT+'}pref')}
        result={}
        for key,(name,kind,*rest) in PREF_FIELDS.items():
            value=prefs.get(name,'')
            if kind=='bool': result[key]=value=='TRUE'
            elif kind=='notbool': result[key]=value!='TRUE'
            elif kind=='date': result[key]=f'{value[:4]}-{value[4:6]}-{value[6:8]}' if re.fullmatch(r'\d{14}Z',value) else ''
            else: result[key]=value
        suppress=prefs.get('zimbraPrefOutOfOfficeSuppressExternalReply')=='TRUE'
        senders=prefs.get('zimbraPrefExternalSendersType','ALL')
        result['vacationAudience']='everyone' if not suppress else 'contacts' if senders=='ALLNOTINAB' else 'company'
        return result
    def save_account_settings(self, token, data):
        if not isinstance(data,dict) or not data or len(data)>len(PREF_FIELDS)+1: raise APIError('Choose a setting to change.')
        values={}
        for key,value in data.items():
            if key=='vacationAudience':
                if value not in ('everyone','company','contacts'): raise APIError('Choose who receives your automatic reply.')
                values['zimbraPrefOutOfOfficeSuppressExternalReply']='FALSE' if value=='everyone' else 'TRUE'
                values['zimbraPrefExternalSendersType']='ALLNOTINAB' if value=='contacts' else 'ALL'
                continue
            if key not in PREF_FIELDS: raise APIError('Unknown setting.')
            name,kind,*rest=PREF_FIELDS[key]; label=rest[1] if len(rest)>1 else 'This setting'
            if kind in ('bool','notbool'):
                if not isinstance(value,bool): raise APIError(label+' must be on or off.')
                values[name]='TRUE' if value==(kind=='bool') else 'FALSE'
            elif kind=='choice':
                if value not in rest[0]: raise APIError(label+' has an unsupported value.')
                values[name]=value
            elif kind=='text':
                if not isinstance(value,str) or len(value)>rest[0]: raise APIError(f'{label} must be at most {rest[0]} characters.')
                values[name]=value
            elif kind=='color':
                if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value): raise APIError('Choose a text colour.')
                values[name]=value.lower()
            elif kind=='emails':
                addresses=[a.strip() for a in str(value).split(',') if a.strip()] if isinstance(value,str) else None
                if addresses is None or len(addresses)>5 or any(len(a)>254 or not EMAIL.fullmatch(a) for a in addresses): raise APIError(label+' must be valid email addresses (up to five).')
                values[name]=','.join(addresses)
            elif kind=='date':
                if value=='': values[name]=''
                elif isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
                    try: time.strptime(value,'%Y-%m-%d')
                    except ValueError: raise APIError(label+' is not a valid date.')
                    values[name]=value.replace('-','')+rest[0]
                else: raise APIError(label+' is not a valid date.')
        if values.get('zimbraPrefOutOfOfficeFromDate') and values.get('zimbraPrefOutOfOfficeUntilDate') and values['zimbraPrefOutOfOfficeUntilDate']<values['zimbraPrefOutOfOfficeFromDate']:
            raise APIError('The last day must be on or after the first day.')
        r=node(ACCOUNT,'ModifyPrefsRequest')
        for key,value in values.items(): r.append(node(ACCOUNT,'pref',{'name':key},value))
        self.call(r,token); return self.account_settings(token)
    def account_info(self, token):
        out=self.call(node(ACCOUNT,'GetInfoRequest',{'sections':'mbox,attrs'}),token)
        attrs={a.get('name'):a.text or '' for a in out.findall('.//{'+ACCOUNT+'}attr')}
        used=out.find('{'+ACCOUNT+'}used'); name=out.find('{'+ACCOUNT+'}name')
        try: quota=int(attrs.get('zimbraMailQuota') or 0)
        except ValueError: quota=0
        flag=lambda key: attrs.get(key)=='TRUE'
        return {'email':name.text if name is not None else '','used':int(used.text) if used is not None and (used.text or '').isdigit() else 0,'quota':quota,
            'features':{'forwarding':flag('zimbraFeatureMailForwardingEnabled'),'filters':flag('zimbraFeatureFiltersEnabled'),'vacation':flag('zimbraFeatureOutOfOfficeReplyEnabled'),
                'changePassword':flag('zimbraFeatureChangePasswordEnabled'),'pop':flag('zimbraPop3Enabled'),'imap':attrs.get('zimbraImapEnabled')!='FALSE'},
            'passwordMinLength':int(attrs.get('zimbraPasswordMinLength') or 6) if (attrs.get('zimbraPasswordMinLength') or '6').isdigit() else 6}
    def change_password(self, token, email, data):
        current=data.get('current'); new=data.get('password')
        if not isinstance(current,str) or not current or len(current)>4096: raise APIError('Enter your current password.')
        if not isinstance(new,str) or not 6<=len(new)<=4096: raise APIError('Choose a new password of at least 6 characters.')
        if new==current: raise APIError('Choose a password that is different from the current one.')
        r=node(ACCOUNT,'ChangePasswordRequest'); r.append(node(ACCOUNT,'account',{'by':'name'},email))
        r.append(node(ACCOUNT,'oldPassword',text=current)); r.append(node(ACCOUNT,'password',text=new))
        try: out=self.call(r,token)
        except APIError as e:
            if e.code=='account.AUTH_FAILED': raise APIError('Your current password is not correct.',400)
            if e.code=='account.INVALID_PASSWORD': raise APIError('The new password does not meet your company password policy.')
            raise
        fresh=out.find('{'+ACCOUNT+'}authToken'); lifetime=out.find('{'+ACCOUNT+'}lifetime')
        return (fresh.text if fresh is not None and fresh.text else token), min(int(lifetime.text)/1000 if lifetime is not None else 3600,3600)
    # ---------- labels (mailbox tags) ----------
    def labels(self, token):
        out=self.call(node(MAIL,'GetTagRequest'),token)
        return {'labels':[{'id':t.get('id'),'name':t.get('name',''),'color':t.get('color') or t.get('rgb') or '','unread':int(t.get('u') or 0),'count':int(t.get('n') or 0)} for t in out.findall('{'+MAIL+'}tag')]}
    def label_action(self, token, data):
        op=data.get('op'); name=str(data.get('name','')).strip()
        valid=lambda: 1<=len(name)<=64 and ',' not in name and not any(ord(c)<32 for c in name)
        if op=='create':
            if not valid(): raise APIError('Enter a label of up to 64 characters without commas.')
            r=node(MAIL,'CreateTagRequest'); r.append(node(MAIL,'tag',{'name':name})); self.call(r,token); return self.labels(token)
        ident=str(data.get('id',''))
        if not re.fullmatch(r'\d{1,10}',ident): raise APIError('Choose a label.')
        attrs={'id':ident}
        if op=='rename':
            if not valid(): raise APIError('Enter a label of up to 64 characters without commas.')
            attrs.update(op='rename',name=name)
        elif op=='delete': attrs['op']='delete'
        elif op=='color':
            color=data.get('color')
            if not isinstance(color,int) or not 0<=color<=9: raise APIError('Choose a label colour.')
            attrs.update(op='color',color=str(color))
        else: raise APIError('Unsupported label operation.')
        r=node(MAIL,'TagActionRequest'); r.append(node(MAIL,'action',attrs)); self.call(r,token); return self.labels(token)
    # ---------- filters and blocked senders ----------
    # Filters run on the mail server as each message arrives, so they work even when no app is
    # open. Blocked senders are filters too: their mail goes straight to Spam.
    def filters(self, token):
        out=self.call(node(MAIL,'GetFilterRulesRequest'),token)
        rules=[];blocked=[];other=0
        for rule in out.iter('{'+MAIL+'}filterRule'):
            parsed=parse_filter(rule)
            if parsed is None: other+=1
            elif parsed.get('blocked'): blocked.append(parsed['blocked'])
            else: rules.append(parsed)
        return {'filters':rules,'blocked':blocked,'unmanaged':other}
    def save_filters(self, token, data):
        filters=data.get('filters'); blocked=data.get('blocked')
        if not isinstance(filters,list) or len(filters)>200: raise APIError('Too many filters (the limit is 200).')
        if not isinstance(blocked,list) or len(blocked)>500: raise APIError('Too many blocked addresses (the limit is 500).')
        current=self.call(node(MAIL,'GetFilterRulesRequest'),token)
        # Rules created in other mail apps are kept exactly as they are.
        keep=[rule for rule in current.iter('{'+MAIL+'}filterRule') if parse_filter(rule) is None]
        built=[build_filter(f,i) for i,f in enumerate(filters)]
        names=[b.get('name') for b in built]
        if len(set(names))!=len(names): raise APIError('Each filter needs a different name.')
        seen=set()
        for address in blocked:
            address=str(address).strip().lower()
            if not address or address in seen: continue
            if len(address)>254 or not (EMAIL.fullmatch(address) or DOMAIN_NAME.fullmatch(address.lstrip('@'))): raise APIError('Blocked entries must be email addresses or domains: '+address[:80])
            seen.add(address); built.insert(0,build_block(address))
        r=node(MAIL,'ModifyFilterRulesRequest'); container=node(MAIL,'filterRules')
        for rule in built+keep: container.append(rule)
        r.append(container); self.call(r,token); return self.filters(token)

FILTER_FOLDERS = {'inbox':'Inbox','archive':'Archive','spam':'Junk','trash':'Trash'}
BLOCK_PREFIX = 'Dmail blocked: '
def build_block(address):
    rule=node(MAIL,'filterRule',{'name':BLOCK_PREFIX+address,'active':'1'})
    tests=node(MAIL,'filterTests',{'condition':'anyof'})
    tests.append(node(MAIL,'headerTest',{'index':'0','header':'from','stringComparison':'contains','value':address}))
    actions=node(MAIL,'filterActions')
    actions.append(node(MAIL,'actionFileInto',{'index':'0','folderPath':'Junk'})); actions.append(node(MAIL,'actionStop',{'index':'1'}))
    rule.append(tests); rule.append(actions); return rule
def build_filter(f, position):
    if not isinstance(f,dict): raise APIError('Invalid filter.')
    name=str(f.get('name','')).strip() or f'Filter {position+1}'
    if len(name)>128 or name.startswith(BLOCK_PREFIX) or any(ord(c)<32 for c in name): raise APIError('Filter names must be at most 128 characters.')
    rule=node(MAIL,'filterRule',{'name':name,'active':'1' if f.get('active',True) else '0'})
    tests=node(MAIL,'filterTests',{'condition':'anyof' if f.get('match')=='any' else 'allof'}); index=0
    def text(key):
        value=f.get(key,'')
        if not isinstance(value,str) or len(value)>1000 or any(ord(c)<32 for c in value): raise APIError('Filter criteria must be plain text of at most 1000 characters.')
        return value.strip()
    for key,header in (('from','from'),('to','to,cc'),('subject','subject')):
        if text(key): tests.append(node(MAIL,'headerTest',{'index':str(index),'header':header,'stringComparison':'contains','value':text(key)})); index+=1
    if text('hasWords'): tests.append(node(MAIL,'bodyTest',{'index':str(index),'value':text('hasWords')})); index+=1
    if text('doesntHave'): tests.append(node(MAIL,'bodyTest',{'index':str(index),'value':text('doesntHave'),'negative':'1'})); index+=1
    if f.get('hasAttachment') is True: tests.append(node(MAIL,'attachmentTest',{'index':str(index)})); index+=1
    size=f.get('sizeOver')
    if size not in (None,'',0):
        if isinstance(size,bool) or not isinstance(size,int) or not 1<=size<=100000: raise APIError('Size must be between 1 and 100000 KB.')
        tests.append(node(MAIL,'sizeTest',{'index':str(index),'numberComparison':'over','s':f'{size}K'})); index+=1
    if not index: raise APIError(f'Filter "{name[:40]}" needs at least one condition.')
    actions=node(MAIL,'filterActions'); a=f.get('actions') if isinstance(f.get('actions'),dict) else {}; index=0
    def add(tag, attrs=None):
        nonlocal index; actions.append(node(MAIL,tag,{'index':str(index),**(attrs or {})})); index+=1
    if a.get('markRead') is True: add('actionFlag',{'flagName':'read'})
    if a.get('star') is True: add('actionFlag',{'flagName':'flagged'})
    label=a.get('label','')
    if label:
        if not isinstance(label,str) or len(label)>64 or ',' in label: raise APIError('Choose a label of up to 64 characters.')
        add('actionTag',{'tagName':label})
    forward=a.get('forward','')
    if forward:
        if not isinstance(forward,str) or not EMAIL.fullmatch(forward.strip()): raise APIError('Enter a valid forwarding address.')
        add('actionRedirect',{'a':forward.strip()})
    folder=a.get('folder','')
    if a.get('delete') is True: add('actionFileInto',{'folderPath':'Trash'})
    elif folder:
        if folder not in FILTER_FOLDERS: raise APIError('Choose a folder for the filter.')
        add('actionFileInto',{'folderPath':FILTER_FOLDERS[folder]})
    if not index: raise APIError(f'Filter "{name[:40]}" needs at least one action.')
    if a.get('stop',True) is not False: add('actionStop')
    rule.append(tests); rule.append(actions); return rule
def parse_filter(rule):
    """Reads back a rule this app wrote; anything else returns None and is left untouched."""
    q=lambda tag:'{'+MAIL+'}'+tag
    name=rule.get('name',''); tests=rule.find(q('filterTests')); actions=rule.find(q('filterActions'))
    if tests is None or actions is None: return None
    if name.startswith(BLOCK_PREFIX):
        return {'blocked':name[len(BLOCK_PREFIX):]}
    f={'name':name,'active':rule.get('active')!='0','match':'any' if tests.get('condition')=='anyof' else 'all','from':'','to':'','subject':'','hasWords':'','doesntHave':'','hasAttachment':False,'sizeOver':0,
       'actions':{'folder':'','markRead':False,'star':False,'label':'','forward':'','delete':False,'stop':False}}
    for t in tests:
        tag=t.tag.split('}')[1]
        if tag=='headerTest' and t.get('stringComparison')=='contains' and t.get('negative')!='1':
            key={'from':'from','to,cc':'to','subject':'subject'}.get(t.get('header'))
            if not key or f[key]: return None
            f[key]=t.get('value','')
        elif tag=='bodyTest':
            key='doesntHave' if t.get('negative')=='1' else 'hasWords'
            if f[key]: return None
            f[key]=t.get('value','')
        elif tag=='attachmentTest' and t.get('negative')!='1': f['hasAttachment']=True
        elif tag=='sizeTest' and t.get('numberComparison')=='over' and re.fullmatch(r'\d+K',t.get('s','')): f['sizeOver']=int(t.get('s')[:-1])
        else: return None
    a=f['actions']; folders={v:k for k,v in FILTER_FOLDERS.items()}
    for t in actions:
        tag=t.tag.split('}')[1]
        if tag=='actionFlag' and t.get('flagName')=='read': a['markRead']=True
        elif tag=='actionFlag' and t.get('flagName')=='flagged': a['star']=True
        elif tag=='actionTag': a['label']=t.get('tagName','')
        elif tag=='actionRedirect': a['forward']=t.get('a','')
        elif tag=='actionFileInto' and t.get('folderPath')=='Trash': a['delete']=True
        elif tag=='actionFileInto' and t.get('folderPath') in folders: a['folder']=folders[t.get('folderPath')]
        elif tag=='actionStop': a['stop']=True
        else: return None
    return f

TIME_ZONES = ('Asia/Kolkata','Asia/Dubai','Asia/Singapore','Asia/Tokyo','Asia/Shanghai','Asia/Karachi','Asia/Dhaka','Asia/Kathmandu','Europe/London','Europe/Berlin','Europe/Paris',
    'America/New_York','America/Chicago','America/Denver','America/Los_Angeles','America/Sao_Paulo','Africa/Johannesburg','Africa/Lagos','Australia/Sydney','Pacific/Auckland','UTC')
FONT_FAMILIES = ('arial, helvetica, sans-serif','times new roman, new york, times, serif','courier new, courier, monaco, monospace','georgia, serif','verdana, helvetica, sans-serif','tahoma, verdana, sans-serif','trebuchet ms, helvetica, sans-serif','comic sans ms, comic sans, sans-serif')
# key: (mailbox preference, kind, rule, label)
PREF_FIELDS = {
    'locale':('zimbraPrefLocale','choice',('','en_US','en_GB','hi'),'Language'),
    'timeZone':('zimbraPrefTimeZoneId','choice',TIME_ZONES,'Time zone'),
    'pageSize':('zimbraPrefMailItemsPerPage','choice',('10','25','50','100'),'Page size'),
    'conversationView':('zimbraPrefGroupMailBy','choice',('conversation','message'),'Conversation view'),
    'externalImages':('zimbraPrefDisplayExternalImages','bool',None,'Images'),
    'snippets':('zimbraPrefShowFragments','bool',None,'Snippets'),
    'autoAddContacts':('zimbraPrefAutoAddAddressEnabled','bool',None,'Auto-complete contacts'),
    'keyboardShortcuts':('zimbraPrefUseKeyboardShortcuts','bool',None,'Keyboard shortcuts'),
    'pollInterval':('zimbraPrefMailPollingInterval','choice',('1m','2m','5m','10m','15m','30m'),'Check for new mail'),
    'readReceipts':('zimbraPrefMailSendReadReceipts','choice',('never','always','prompt'),'Read receipts'),
    'saveToSent':('zimbraPrefSaveToSent','bool',None,'Save sent messages'),
    'fontFamily':('zimbraPrefHtmlEditorDefaultFontFamily','choice',FONT_FAMILIES,'Font'),
    'fontSize':('zimbraPrefHtmlEditorDefaultFontSize','choice',('10pt','12pt','14pt','18pt'),'Text size'),
    'fontColor':('zimbraPrefHtmlEditorDefaultFontColor','color',None,'Text colour'),
    'replyToEnabled':('zimbraPrefReplyToEnabled','bool',None,'Reply-to'),
    'replyTo':('zimbraPrefReplyToAddress','emails',None,'Reply-to address'),
    'forwardTo':('zimbraPrefMailForwardingAddress','emails',None,'Forwarding address'),
    'forwardKeepCopy':('zimbraPrefMailLocalDeliveryDisabled','notbool',None,'Keep a copy'),
    'popDelete':('zimbraPrefPop3DeleteOption','choice',('keep','read','trash','delete'),'POP download action'),
    'vacationOn':('zimbraPrefOutOfOfficeReplyEnabled','bool',None,'Out-of-office reply'),
    'vacationMessage':('zimbraPrefOutOfOfficeReply','text',8192,'Out-of-office message'),
    'vacationFrom':('zimbraPrefOutOfOfficeFromDate','date','000000Z','First day'),
    'vacationUntil':('zimbraPrefOutOfOfficeUntilDate','date','235959Z','Last day'),
    'vacationExternalOn':('zimbraPrefOutOfOfficeExternalReplyEnabled','bool',None,'Separate reply for outside senders'),
    'vacationExternalMessage':('zimbraPrefOutOfOfficeExternalReply','text',8192,'Reply for outside senders'),
    'vacationEvery':('zimbraPrefOutOfOfficeCacheDuration','choice',('1d','4d','7d'),'Reply frequency'),
}
UI_CHOICES = {'undoSend':(0,5,10,20,30),'defaultReply':('reply','replyall'),'buttonLabels':('icons','text'),'notifications':('all','important','off'),
    'inboxType':('default','unread','starred','important'),'readingPane':('off','right','bottom'),'autoAdvance':('off','next','previous'),'density':('comfortable','compact'),'starPreset':('one','four','all')}
UI_FLAGS = ('hoverActions','sendArchive','spellcheck','autocorrect','indicators','importanceMarkers','templates','unreadBadge','autoAdvanceOn','undoSendOn','smartRefresh')
UI_FOLDERS = ('inbox','starred','sent','drafts','archive','spam','trash','unread','attach','important')
def clean_ui_settings(data):
    """Display preferences the mail server has no field for; each one is bounded."""
    if not isinstance(data,dict): raise APIError('Invalid settings.')
    out={}
    for key,value in data.items():
        if key in UI_CHOICES:
            if isinstance(value,bool) or value not in UI_CHOICES[key]: raise APIError('Invalid value for '+key+'.')
            out[key]=value
        elif key in UI_FLAGS:
            if not isinstance(value,bool): raise APIError('Invalid value for '+key+'.')
            out[key]=value
        elif key=='hiddenFolders':
            if not isinstance(value,list) or any(v not in UI_FOLDERS for v in value): raise APIError('Invalid label visibility.')
            out[key]=sorted(set(value))
        elif key=='templateList':
            if not isinstance(value,list) or len(value)>50: raise APIError('You can keep up to 50 templates.')
            items=[]
            for t in value:
                if not isinstance(t,dict) or not isinstance(t.get('name'),str) or not isinstance(t.get('body'),str): raise APIError('Invalid template.')
                name=t['name'].strip()
                if not 1<=len(name)<=100 or len(t['body'])>20000: raise APIError('Template names must be at most 100 characters and bodies 20000.')
                items.append({'name':name,'subject':str(t.get('subject',''))[:300],'body':safe_html(t['body'])})
            out[key]=items
        else: raise APIError('Unknown setting: '+str(key)[:40])
    if len(json.dumps(out))>1200000: raise APIError('Settings are too large.')
    return out

SERVICE_LABELS = {'mailbox':'Mailbox store','mta':'Mail delivery (SMTP)','antispam':'Spam filter','antivirus':'Virus scanner','amavis':'Content filter',
    'logger':'Activity log','memcached':'Cache','stats':'Statistics','ldap':'Directory','proxy':'Web proxy','opendkim':'DKIM signing','service':'Web services',
    'zimlet':'Extensions','zimbraAdmin':'Admin service','zimbra':'Web mail service','snmp':'Monitoring','spell':'Spell check','dnscache':'DNS cache',
    'cbpolicyd':'Sending policy','convertd':'Document conversion','imapd':'IMAP service','onlyoffice':'Document editing'}
UUID = re.compile(r'[a-fA-F0-9-]{36}')
EMAIL = re.compile(r'[^\s<>@,]+@[^\s<>@,]+\.[^\s<>@,]+')
def cos_fields(a):
    def number(name):
        try: return int(a.get(name) or 0)
        except ValueError: return 0
    return {'quotaMB':round(number('zimbraMailQuota')/1048576),'passwordMinLength':number('zimbraPasswordMinLength'),'passwordMaxAgeDays':number('zimbraPasswordMaxAge')}
def whole(data, key, low, high, message):
    value=data.get(key)
    if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high: raise APIError(message)
    return value

class Admin(Zimbra):
    """Separate, upstream-authorized admin session; no shared service credentials."""
    mail_host='localhost'; dkim_dir=None
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
    def overview(self, token, scope=None):
        """Everything the admin may see; a company admin (scope=its domain) sees only that domain."""
        def in_domain(request):
            if scope: request.append(node(ADMIN,'domain',{'by':'name'},scope))
            return request
        users=self.call(in_domain(node(ADMIN,'GetAllAccountsRequest')),token)
        if scope:
            domains=node(ADMIN,'GetAllDomainsResponse')
            found=self.call(in_domain(node(ADMIN,'GetDomainRequest')),token).find('{'+ADMIN+'}domain')
            if found is not None: domains.append(found)
        else: domains=self.call(node(ADMIN,'GetAllDomainsRequest'),token)
        def attributes(element):
            return {a.get('n'):a.text or '' for a in element.findall('{'+ADMIN+'}a')}
        accounts=[]
        for account in users.findall('{'+ADMIN+'}account'):
            a=attributes(account)
            if a.get('zimbraIsSystemResource')=='TRUE': continue
            accounts.append({'id':account.get('id'),'email':account.get('name'),
                'name':a.get('displayName') or account.get('name'),
                'status':a.get('zimbraAccountStatus','active'),
                'role':'Admin' if a.get('zimbraIsAdminAccount')=='TRUE' else 'Domain admin' if a.get('zimbraIsDelegatedAdminAccount')=='TRUE' else 'User',
                'aliases':[v.text for v in account.findall('{'+ADMIN+'}a') if v.get('n')=='zimbraMailAlias' and v.text],
                'quota':a.get('zimbraMailQuota','0')})
        def optional(build):
            try: return build()
            except APIError: return None
        usage=optional(lambda:{a.get('id'):(int(a.get('used','0')),int(a.get('limit','0'))) for a in self.call(node(ADMIN,'GetQuotaUsageRequest',{'allServers':'1',**({'domain':scope} if scope else {})}),token).findall('{'+ADMIN+'}account')}) or {}
        for account,element in zip(accounts,[x for x in users.findall('{'+ADMIN+'}account') if attributes(x).get('zimbraIsSystemResource')!='TRUE']):
            a=attributes(element)
            account.update({'cosId':a.get('zimbraCOSId',''),'forward':a.get('zimbraPrefMailForwardingAddress',''),
                'keepCopy':a.get('zimbraPrefMailLocalDeliveryDisabled')!='TRUE','lastLogin':a.get('zimbraLastLogonTimestamp',''),
                'created':a.get('zimbraCreateTimestamp',''),'used':usage.get(account['id'],(None,None))[0],'limit':usage.get(account['id'],(None,None))[1]})
        def plans():
            return [{'id':c.get('id'),'name':c.get('name'),**cos_fields(attributes(c))} for c in self.call(node(ADMIN,'GetAllCosRequest'),token).findall('{'+ADMIN+'}cos')]
        def lists():
            return [{'id':d.get('id'),'email':d.get('name'),'name':attributes(d).get('displayName','')} for d in self.call(in_domain(node(ADMIN,'GetAllDistributionListsRequest')),token).findall('{'+ADMIN+'}dl')]
        def services():
            # Internal component names never leave the server; the panel shows product-neutral labels.
            return [{'server':x.get('server'),'service':SERVICE_LABELS.get(x.get('service'),'Mail service component'),'running':(x.text or '').strip()=='1'} for x in self.call(node(ADMIN,'GetServiceStatusRequest'),token).findall('.//{'+ADMIN+'}status')]
        def settings():
            config=self.call(node(ADMIN,'GetAllConfigRequest'),token)
            a=attributes(config)
            return {'maxMessageMB':round(int(a.get('zimbraMtaMaxMessageSize') or 0)/1048576),'uploadMaxMB':round(int(a.get('zimbraFileUploadMaxSize') or 0)/1048576),
                'blockedExtensions':sorted({v.text for v in config.findall('{'+ADMIN+'}a') if v.get('n')=='zimbraMtaBlockedExtension' and v.text})}
        return {'users':accounts,'domains':[{'id':d.get('id'),'domain':d.get('name'),
            'status':attributes(d).get('zimbraDomainStatus','active')}
            for d in domains.findall('{'+ADMIN+'}domain')],
            'plans':None if scope else optional(plans),'lists':optional(lists),'services':None if scope else optional(services),
            'settings':None if scope else optional(settings),'scope':scope}
    def action(self, token, data, actor, scope=None, elevate=None):
        """elevate() returns a service-admin token for the few admin-flag changes a company admin may
        request but cannot make with its own rights; it is used only after the target was checked in scope."""
        op=data.get('op')
        if scope and op in ('create_domain','domain_status','plan_update','set_plan','settings_update'):
            raise APIError('This setting is managed by the Dejoiy platform team.',403)
        def own(address):
            # Company admins may only touch addresses in their own domain (the server enforces this too).
            if scope and not address.lower().endswith('@'+scope): raise APIError('You can only manage addresses in '+scope+'.',403)
            return address
        def privileged():
            if not scope: return token
            if not elevate: raise APIError('Role changes are not available right now.',503)
            return elevate()
        def grant(email, domain, revoke=False):
            r=node(ADMIN,'RevokeRightRequest' if revoke else 'GrantRightRequest')
            r.append(node(ADMIN,'target',{'type':'domain','by':'name'},domain))
            r.append(node(ADMIN,'grantee',{'type':'usr','by':'name'},email))
            r.append(node(ADMIN,'right',{'canDelegate':'1'},'domainAdminRights'))
            try: self.call(r,privileged())
            except APIError as e:
                if not (revoke and e.code=='account.NO_SUCH_GRANT'): raise
        def require_global_admin():
            request=node(ADMIN,'GetAccountRequest')
            request.append(node(ADMIN,'account',{'by':'name'},actor))
            response=self.call(request,token)
            account=response.find('{'+ADMIN+'}account')
            if account is None or not any(a.get('n')=='zimbraIsAdminAccount' and a.text=='TRUE' for a in account.findall('{'+ADMIN+'}a')):
                raise APIError('Only a full administrator can assign administrator roles.',403)
        def account_role():
            role=data.get('role','User')
            if role not in ('User','Domain admin','Admin') or (scope and role=='Admin'): raise APIError('Select a valid mailbox role.')
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
            own(email); role=account_role()
            if role=='Admin': require_global_admin()
            r=node(ADMIN,'CreateAccountRequest')
            r.append(node(ADMIN,'name',text=email)); r.append(node(ADMIN,'password',text=password()))
            name=str(data.get('name','')).strip()
            if not name or len(name)>200: raise APIError('Enter a display name of up to 200 characters.')
            r.append(node(ADMIN,'a',{'n':'displayName'},name))
            if not scope: r.append(node(ADMIN,'a',{'n':'zimbraIsAdminAccount'},'TRUE' if role=='Admin' else 'FALSE'))
            if role=='Domain admin':
                created=self.call(r,token).find('{'+ADMIN+'}account')
                flag=node(ADMIN,'ModifyAccountRequest'); flag.append(node(ADMIN,'id',text=created.get('id') if created is not None else ''))
                flag.append(node(ADMIN,'a',{'n':'zimbraIsDelegatedAdminAccount'},'TRUE')); self.call(flag,privileged())
                grant(email,email.split('@')[1]); return {'ok':True}
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
            own(account.get('name',''))
            if op=='status':
                status=data.get('status')
                if status not in ('active','locked','maintenance'): raise APIError('Invalid mailbox status.')
                if account.get('name','').lower()==actor.lower() and status!='active':
                    raise APIError('You cannot lock your own administrator mailbox.')
                r=node(ADMIN,'ModifyAccountRequest'); r.append(node(ADMIN,'id',text=ident))
                r.append(node(ADMIN,'a',{'n':'zimbraAccountStatus'},status))
            elif op=='role':
                role=account_role(); name=account.get('name','')
                if name.lower()==actor.lower(): raise APIError('You cannot change your own administrator role.')
                if not scope: require_global_admin()
                if any(a.get('n')=='zimbraIsAdminAccount' and a.text=='TRUE' for a in account.findall('{'+ADMIN+'}a')) and scope: raise APIError('Only the Dejoiy platform team can change this mailbox.',403)
                r=node(ADMIN,'ModifyAccountRequest');r.append(node(ADMIN,'id',text=ident))
                if not scope: r.append(node(ADMIN,'a',{'n':'zimbraIsAdminAccount'},'TRUE' if role=='Admin' else 'FALSE'))
                r.append(node(ADMIN,'a',{'n':'zimbraIsDelegatedAdminAccount'},'TRUE' if role=='Domain admin' else 'FALSE'))
                self.call(r,privileged())
                grant(name,name.split('@')[1],revoke=role!='Domain admin')
                return {'ok':True}
            elif op=='quota':
                quota=data.get('quotaMB')
                if isinstance(quota,bool) or not isinstance(quota,int) or not 0<=quota<=10485760: raise APIError('Quota must be a whole number from 0 to 10485760 MB; 0 means unlimited.')
                r=node(ADMIN,'ModifyAccountRequest');r.append(node(ADMIN,'id',text=ident))
                r.append(node(ADMIN,'a',{'n':'zimbraMailQuota'},str(quota*1024*1024)))
            elif op in ('add_alias','remove_alias'):
                alias=str(data.get('alias','')).strip().lower()
                if len(alias)>320 or not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+',alias): raise APIError('Enter a valid alias email address.')
                own(alias)
                r=node(ADMIN,'AddAccountAliasRequest' if op=='add_alias' else 'RemoveAccountAliasRequest')
                r.append(node(ADMIN,'id',text=ident));r.append(node(ADMIN,'alias',text=alias))
            else:
                r=node(ADMIN,'SetPasswordRequest'); r.append(node(ADMIN,'id',text=ident))
                r.append(node(ADMIN,'newPassword',text=password()))
        elif op in ('delete_user','set_name','forward','set_plan'):
            ident=str(data.get('id',''))
            if not UUID.fullmatch(ident): raise APIError('Invalid mailbox selection.')
            lookup=node(ADMIN,'GetAccountRequest'); lookup.append(node(ADMIN,'account',{'by':'id'},ident))
            account=self.call(lookup,token).find('{'+ADMIN+'}account')
            if account is None: raise APIError('Mailbox not found.',404)
            own(account.get('name',''))
            if op=='delete_user':
                if account.get('name','').lower()==actor.lower(): raise APIError('You cannot delete your own administrator mailbox.')
                if str(data.get('confirm','')).lower()!=account.get('name','').lower(): raise APIError('Type the mailbox address to confirm deletion.')
                r=node(ADMIN,'DeleteAccountRequest',{'id':ident})
            else:
                r=node(ADMIN,'ModifyAccountRequest'); r.append(node(ADMIN,'id',text=ident))
                if op=='set_name':
                    name=str(data.get('name','')).strip()
                    if not name or len(name)>200: raise APIError('Enter a display name of up to 200 characters.')
                    r.append(node(ADMIN,'a',{'n':'displayName'},name))
                elif op=='forward':
                    targets=[t.strip().lower() for t in str(data.get('forward','')).split(',') if t.strip()]
                    if len(targets)>10 or any(len(t)>320 or not EMAIL.fullmatch(t) for t in targets): raise APIError('Enter up to 10 valid forwarding addresses, separated by commas.')
                    if not isinstance(data.get('keepCopy',True),bool): raise APIError('Invalid copy setting.')
                    r.append(node(ADMIN,'a',{'n':'zimbraPrefMailForwardingAddress'},','.join(targets)))
                    r.append(node(ADMIN,'a',{'n':'zimbraPrefMailLocalDeliveryDisabled'},'FALSE' if data.get('keepCopy',True) or not targets else 'TRUE'))
                else:
                    plan=str(data.get('planId',''))
                    if plan and not UUID.fullmatch(plan): raise APIError('Select a valid plan.')
                    r.append(node(ADMIN,'a',{'n':'zimbraCOSId'},plan))
        elif op=='dns_records':
            domain=str(data.get('domain','')).strip().lower()
            if not DOMAIN_NAME.fullmatch(domain) or (scope and domain!=scope): raise APIError('You can only check your own domain.',403)
            lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'name'},domain)); self.call(lookup,token)
            return {'domain':domain,'records':domain_records(domain,self.mail_host,self.dkim_dir)}
        elif op=='domain_status':
            ident=str(data.get('id',''));status=data.get('status')
            if not UUID.fullmatch(ident): raise APIError('Invalid domain selection.')
            if status not in ('active','locked','maintenance','suspended'): raise APIError('Invalid domain status.')
            r=node(ADMIN,'ModifyDomainRequest'); r.append(node(ADMIN,'id',text=ident)); r.append(node(ADMIN,'a',{'n':'zimbraDomainStatus'},status))
        elif op=='create_list':
            email=str(data.get('email','')).strip().lower();name=str(data.get('name','')).strip()
            if len(email)>320 or not EMAIL.fullmatch(email): raise APIError('Enter a valid mailing list address.')
            own(email)
            if len(name)>200: raise APIError('List name must be at most 200 characters.')
            r=node(ADMIN,'CreateDistributionListRequest'); r.append(node(ADMIN,'name',text=email))
            if name: r.append(node(ADMIN,'a',{'n':'displayName'},name))
        elif op in ('delete_list','list_members','add_member','remove_member'):
            ident=str(data.get('id',''))
            if not UUID.fullmatch(ident): raise APIError('Invalid mailing list selection.')
            if op=='list_members':
                lookup=node(ADMIN,'GetDistributionListRequest',{'limit':'0'}); lookup.append(node(ADMIN,'dl',{'by':'id'},ident))
                found=self.call(lookup,token).find('{'+ADMIN+'}dl')
                if found is None: raise APIError('Mailing list not found.',404)
                return {'members':sorted(m.text for m in found.findall('{'+ADMIN+'}dlm') if m.text)}
            if scope:
                lookup=node(ADMIN,'GetDistributionListRequest',{'limit':'1'}); lookup.append(node(ADMIN,'dl',{'by':'id'},ident))
                found=self.call(lookup,token).find('{'+ADMIN+'}dl')
                if found is None: raise APIError('Mailing list not found.',404)
                own(found.get('name',''))
            if op=='delete_list': r=node(ADMIN,'DeleteDistributionListRequest',{'id':ident})
            else:
                member=str(data.get('member','')).strip().lower()
                if len(member)>320 or not EMAIL.fullmatch(member): raise APIError('Enter a valid member address.')
                r=node(ADMIN,'AddDistributionListMemberRequest' if op=='add_member' else 'RemoveDistributionListMemberRequest')
                r.append(node(ADMIN,'id',text=ident)); r.append(node(ADMIN,'dlm',text=member))
        elif op=='plan_update':
            ident=str(data.get('id',''))
            if not UUID.fullmatch(ident): raise APIError('Invalid plan selection.')
            quota=whole(data,'quotaMB',0,10485760,'Storage must be a whole number from 0 to 10485760 MB; 0 means unlimited.')
            minimum=whole(data,'passwordMinLength',6,64,'Minimum password length must be from 6 to 64.')
            age=whole(data,'passwordMaxAgeDays',0,3650,'Password expiry must be from 0 to 3650 days; 0 means never.')
            r=node(ADMIN,'ModifyCosRequest'); r.append(node(ADMIN,'id',text=ident))
            for name,value in (('zimbraMailQuota',quota*1048576),('zimbraPasswordMinLength',minimum),('zimbraPasswordMaxAge',age)): r.append(node(ADMIN,'a',{'n':name},str(value)))
        elif op=='settings_update':
            require_global_admin()
            size=whole(data,'maxMessageMB',1,100,'Maximum message size must be from 1 to 100 MB.')
            upload=whole(data,'uploadMaxMB',1,100,'Maximum upload size must be from 1 to 100 MB.')
            extensions=data.get('blockedExtensions')
            if not isinstance(extensions,list) or len(extensions)>200 or any(not isinstance(x,str) or not re.fullmatch(r'[a-z0-9]{1,12}',x) for x in extensions): raise APIError('Blocked file types must be short extensions like exe or js.')
            r=node(ADMIN,'ModifyConfigRequest')
            r.append(node(ADMIN,'a',{'n':'zimbraMtaMaxMessageSize'},str(size*1048576)))
            r.append(node(ADMIN,'a',{'n':'zimbraFileUploadMaxSize'},str(upload*1048576)))
            for x in sorted(set(extensions)) or ['']: r.append(node(ADMIN,'a',{'n':'zimbraMtaBlockedExtension'},x))
        else: raise APIError('Unsupported administration operation.')
        self.call(r,token)
        return {'ok':True}

class Handler(SimpleHTTPRequestHandler):
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.webmanifest':'application/manifest+json','.js':'text/javascript'}
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def log_message(self, *args): pass  # Never log passwords, session IDs or message data.
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','same-origin')
        if urllib.parse.urlsplit(self.path).path in ADMIN_ASSETS: self.send_header('Cache-Control','no-store')
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
                if self.path=='/api/appearance': return self.reply(200,self.server.appearance.get(self.account(s)))
                if self.path=='/api/settings':
                    return self.reply(200,{'mailbox':self.server.zimbra.account_settings(s['token']),'ui':self.server.ui_settings.get(self.account(s)),
                        'account':self.server.zimbra.account_info(s['token']),'server':{'host':self.server.mail_host}})
                if self.path=='/api/account': return self.reply(200,self.server.zimbra.account_info(s['token']))
                if self.path=='/api/labels': return self.reply(200,self.server.zimbra.labels(s['token']))
                if self.path=='/api/filters': return self.reply(200,self.server.zimbra.filters(s['token']))
                if self.path=='/api/avatars': return self.reply(200,{'avatars':self.server.avatars.versions(self.domain(s))})
                if self.path.startswith('/api/avatar?'):
                    email=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('email',[''])[0].strip().lower()
                    # Photos are only shared inside a company: other tenants' mailboxes stay invisible.
                    found=self.server.avatars.get(email) if EMAIL.fullmatch(email) and email.rsplit('@',1)[1]==self.domain(s) else None
                    if not found: raise APIError('No photo',404)
                    return self.image(found[1],IMAGE_MIME[found[0]],'private, max-age=31536000, immutable')
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
                    client,token,scope=self.admin_session(s)
                    return self.reply(200,client.overview(token,scope))
                raise APIError('Not found',404)
            except APIError as e: return self.reply(e.status,{'error':str(e)})
            except (ValueError,TypeError): return self.reply(400,{'error':'Invalid request'})
            except Exception: return self.reply(502,{'error':'Mail operation failed. Try again later.'})
        path=urllib.parse.urlsplit(self.path).path
        if path.startswith('/media/'):
            raw=self.server.media.get(path[len('/media/'):])
            if raw is None: return self.send_error(404)
            return self.image(raw,IMAGE_MIME[path.rsplit('.',1)[1]],'public, max-age=31536000, immutable')
        if path=='/admin/':
            return self.redirect('/admin')
        if path=='/signup':
            self.path='/signup.html'
        if path=='/admin' or path in ADMIN_ASSETS:
            # The console and its code are only served to signed-in administrators.
            try: _,s=self.session()
            except APIError: return self.redirect('/?next=admin') if path=='/admin' else self.send_error(404)
            if s['user'].get('isAdmin') is not True: return self.redirect('/') if path=='/admin' else self.send_error(404)
            if path=='/admin': self.path='/admin.html'
        super().do_GET()
    def image(self, raw, mime, cache):
        self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control',cache); self.send_header('Content-Security-Policy',"default-src 'none'; sandbox")
        self.end_headers(); self.wfile.write(raw)
    def domain(self, session):
        email=session['user']['email'].lower()
        return email.rsplit('@',1)[1] if '@' in email else ''
    def redirect(self, location):
        self.send_response(302); self.send_header('Location',location); self.send_header('Cache-Control','no-store'); self.end_headers()
    def account(self, session):
        # Sessions created before account ids were recorded fall back to the signed-in address.
        return session.get('account') or session['user']['email'].lower()
    def start_session(self, email, password):
        token,lifetime=self.server.zimbra.login(email,password)
        s={'token':token,'expires':time.time()+lifetime,'csrf':secrets.token_urlsafe(32),'user':{'email':email,'name':email.split('@')[0],'signature':''}}
        s['user'].update(self.server.zimbra.capabilities(token))
        account=self.server.zimbra.account_id(token)
        s['account']=account if isinstance(account,str) and account else email.lower()
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
    def signup(self, op, data):
        provisioner=getattr(self.server,'provisioner',None)
        if not provisioner: raise APIError('Company sign-up is not open yet.',503)
        if op=='start':
            company=str(data.get('company','')).strip(); domain=str(data.get('domain','')).strip().lower().rstrip('.')
            name=str(data.get('name','')).strip(); local=str(data.get('localPart','')).strip().lower()
            if not 1<=len(company)<=120: raise APIError('Enter your company name.')
            if len(domain)>253 or not DOMAIN_NAME.fullmatch(domain): raise APIError('Enter your company domain, like acme.com.')
            if domain in FREE_MAIL or any(domain==r or domain.endswith('.'+r) for r in self.server.reserved_domains): raise APIError('Use a domain your company owns.')
            if not 1<=len(name)<=200: raise APIError('Enter your name.')
            if not LOCAL_PART.fullmatch(local): raise APIError('Choose an address made of letters, numbers, dots, dashes or underscores.')
            if provisioner.domain_exists(domain): raise APIError('This domain already uses Dejoiy Mail. Ask its administrator to add you.',409)
            token=secrets.token_urlsafe(24)
            pending={'company':company,'domain':domain,'name':name,'email':local+'@'+domain,'code':'dejoiy-verification='+secrets.token_hex(16)}
            self.server.signups.put(token,pending)
            return self.reply(200,{'token':token,'domain':domain,'email':pending['email'],'record':{'type':'TXT','host':'@','value':pending['code']}})
        token=str(data.get('token',''))
        pending=self.server.signups.get(token) if 20<=len(token)<=64 else None
        if not pending: raise APIError('This sign-up has expired. Start again.',404)
        if op not in ('check','complete'): raise APIError('Not found',404)
        verified=pending['code'] in txt_records(pending['domain'])
        if op=='check':
            return self.reply(200,{'verified':verified,'domain':pending['domain'],'email':pending['email'],'company':pending['company'],'record':{'type':'TXT','host':'@','value':pending['code']}})
        password=data.get('password')
        if not isinstance(password,str) or not 8<=len(password)<=4096: raise APIError('Choose a password of at least 8 characters.')
        if not verified: raise APIError('We could not find the TXT record yet. DNS changes can take a few minutes.',409)
        if provisioner.domain_exists(pending['domain']): raise APIError('This domain already uses Dejoiy Mail.',409)
        provisioner.provision(pending['domain'],pending['company'],pending['email'],pending['name'],password)
        self.server.signups.delete(token)
        return self.start_session(pending['email'],password)
    def admin_session(self, session):
        client=getattr(self.server,'admin',None)
        if not client: raise APIError('Mail administration is not configured on this server.',503)
        if not session.get('admin_token') or session.get('admin_expires',0)<=time.time():
            raise APIError('Sign in to Dejoiy Mail Admin to continue.',403)
        return client,session['admin_token'],session.get('admin_scope')
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
            if self.path in ('/api/login','/api/admin/login') or self.path.startswith('/api/signup/'):
                with LOCK:
                    now=time.time(); attempts=self.server.attempts
                    for key in list(attempts):
                        attempts[key]=[t for t in attempts[key] if t>now-60]
                        if not attempts[key]: del attempts[key]
                    key=self.client_address[0]
                    if ipaddress.ip_address(key).is_loopback and self.headers.get('X-Real-IP'):
                        key=str(ipaddress.ip_address(self.headers['X-Real-IP']))
                    # Sign-up polls DNS, so it gets its own, larger allowance than password attempts.
                    signup=self.path.startswith('/api/signup/'); key+='#signup' if signup else ''
                    if len(attempts.get(key,[]))>=(30 if signup else 10): raise APIError('Too many attempts; wait one minute',429)
                    attempts.setdefault(key,[]).append(now)
            if self.path.startswith('/api/signup/'): return self.signup(self.path[len('/api/signup/'):],data)
            if self.path=='/api/login':
                email=str(data.get('email','')).strip(); password=str(data.get('password',''))
                if not email or len(email)>320 or not password or len(password)>4096: raise APIError('Enter an email and password')
                return self.start_session(email,password)
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
                    # Full administrators see everything; company (domain) admins only their own domain.
                    s.update(admin_token=token,admin_expires=time.time()+min(lifetime,900),
                        admin_scope=None if s['user'].get('canManageRoles') else s['user']['email'].lower().rsplit('@',1)[1])
                    SESSIONS[sid]=s
                return self.reply(200,{'ok':True})
            if self.path=='/api/admin/logout':
                with LOCK:
                    s.pop('admin_token',None); s.pop('admin_expires',None)
                    SESSIONS[sid]=s
                return self.reply(200,{'ok':True})
            if self.path=='/api/admin/action':
                client,token,scope=self.admin_session(s)
                provisioner=getattr(self.server,'provisioner',None)
                return self.reply(200,client.action(token,data,s['user']['email'],scope,provisioner.token if provisioner else None))
            if self.path=='/api/send': return self.reply(200,self.server.zimbra.write_message(s['token'],data))
            if self.path=='/api/draft': return self.reply(200,self.server.zimbra.write_message(s['token'],data,True))
            if self.path=='/api/action': return self.reply(200,self.server.zimbra.action(s['token'],data))
            if self.path=='/api/contacts': return self.reply(200,self.server.zimbra.contact_action(s['token'],data))
            if self.path=='/api/preferences': return self.reply(200,self.server.zimbra.save_preferences(s['token'],data))
            if self.path=='/api/settings':
                result={}
                if 'mailbox' in data: result['mailbox']=self.server.zimbra.save_account_settings(s['token'],data['mailbox'])
                if 'ui' in data:
                    merged={**self.server.ui_settings.get(self.account(s)),**clean_ui_settings(data['ui'])}
                    self.server.ui_settings.put(self.account(s),clean_ui_settings(merged)); result['ui']=merged
                if not result: raise APIError('Choose a setting to change.')
                return self.reply(200,result)
            if self.path=='/api/labels': return self.reply(200,self.server.zimbra.label_action(s['token'],data))
            if self.path=='/api/filters': return self.reply(200,self.server.zimbra.save_filters(s['token'],data))
            if self.path=='/api/password':
                token,lifetime=self.server.zimbra.change_password(s['token'],s['user']['email'],data)
                with LOCK:
                    if sid in SESSIONS: s.update(token=token,expires=time.time()+lifetime); SESSIONS[sid]=s
                return self.reply(200,{'ok':True})
            if self.path=='/api/appearance':
                self.server.appearance.put(self.account(s),clean_appearance(data)); return self.reply(200,{'ok':True})
            if self.path=='/api/avatar':
                email=s['user']['email'].lower()
                if not EMAIL.fullmatch(email): raise APIError('Sign in with your full email address to set a profile photo.')
                if data.get('image')=='':
                    self.server.avatars.delete(email); return self.reply(200,{'ok':True,'version':None})
                ext,raw=decode_image(data.get('image'),('png','jpeg','webp'),MAX_AVATAR_BYTES,'Profile photo')
                return self.reply(200,{'ok':True,'version':self.server.avatars.put(email,ext,raw)})
            if self.path=='/api/signature-image':
                ext,raw=decode_image(data.get('image'),('png','jpeg','gif'),MAX_SIGNATURE_IMAGE_BYTES,'Signature image')
                name=self.server.media.save(self.account(s),ext,raw)
                return self.reply(200,{'url':self.server.app_origin+'/media/'+name})
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
    server.appearance=AppearanceStore(os.environ.get('APPEARANCE_DB') or (str(Path(os.environ['SESSION_DB']).with_name('appearance.sqlite')) if os.environ.get('SESSION_DB') else None))
    url=os.environ.get('ZIMBRA_URL'); server.zimbra=Zimbra(url) if url else None
    server.ui_settings=AppearanceStore((str(Path(os.environ['SESSION_DB']).with_name('settings.sqlite')) if os.environ.get('SESSION_DB') else None),'ui_settings')
    server.mail_host=os.environ.get('MAIL_HOST') or parsed.hostname
    state_dir=Path(os.environ['SESSION_DB']).parent if os.environ.get('SESSION_DB') else None
    server.avatars=AvatarStore(str(state_dir/'avatars.sqlite') if state_dir else None)
    server.media=MediaStore(str(state_dir/'media') if state_dir else None)
    if server.zimbra: server.zimbra.media_prefix=server.app_origin+'/media/'
    admin_url=os.environ.get('ZIMBRA_ADMIN_URL'); server.admin=Admin(admin_url) if admin_url else None
    state=Path(os.environ['SESSION_DB']).parent if os.environ.get('SESSION_DB') else None
    if server.admin:
        server.admin.mail_host=os.environ.get('MAIL_HOST') or urllib.parse.urlsplit(origin).hostname
        server.admin.dkim_dir=os.environ.get('DKIM_DIR') or (str(state/'dkim') if state else None)
    server.signups=SignupStore(str(state/'signups.sqlite') if state else None)
    server.reserved_domains={d.strip().lower() for d in os.environ.get('RESERVED_DOMAINS','dejoiy.com').split(',') if d.strip()}
    server.provisioner=Provisioner(server.admin,os.environ['PROVISION_ADMIN'],os.environ['PROVISION_ADMIN_PASSWORD']) if server.admin and os.environ.get('PROVISION_ADMIN') and os.environ.get('PROVISION_ADMIN_PASSWORD') else None
    print(f'Dejoiy Mail: {origin}; backend '+('configured' if url else 'requires ZIMBRA_URL'))
    server.serve_forever()

if __name__=='__main__': serve()
