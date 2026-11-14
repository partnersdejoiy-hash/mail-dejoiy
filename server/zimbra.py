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
import socket
import base64
import hashlib
import hmac
import binascii
from collections.abc import MutableMapping
import urllib.request
import urllib.error
import http.client
import urllib.parse
import xml.etree.ElementTree as ET
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import dcalendar
import zconsole
from webhooks import Webhooks, WebhookError
from newmail import NewMailWatcher
from automations import Automations, AutomationError
from apitokens import ApiTokens, TokenError, SCOPES as API_SCOPES
from undelivered import Undelivered
from html.parser import HTMLParser

SOAP = 'http://www.w3.org/2003/05/soap-envelope'
MAIL = 'urn:zimbraMail'
ACCOUNT = 'urn:zimbraAccount'
ADMIN = 'urn:zimbraAdmin'
FOLDERS = {'inbox':'2','sent':'5','drafts':'6','spam':'4','trash':'3'}
MAX_ATTACHMENT_BYTES=15*1024*1024
MAX_REQUEST_BYTES=22*1024*1024

def attachment_limits(message_bytes, upload_bytes):
    """What a person can really attach, from the server's own limits (Zimbra GetInfo attSizeLimit =
    MTA message limit, docSizeLimit = upload limit). Attachments grow ~37% when encoded for mail
    (base64 + line breaks) and the text/HTML body needs room, so 10 MB of MTA limit is ~7 MB of files."""
    def num(v):
        try: return int(v) if v is not None and int(v)>0 else 0
        except (TypeError,ValueError): return 0
    mta, upload = num(message_bytes), num(upload_bytes)
    usable = MAX_ATTACHMENT_BYTES
    if mta: usable = min(usable, int((mta-256*1024)/1.37))
    if upload: usable = min(usable, upload)
    return {'messageBytes':mta or None,'uploadBytes':upload or None,'attachmentBytes':max(usable,0)}

SEND_FAILED_KIND='send_failed'  # audit kind for a web send the server refused (kept in Drafts)
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
    accent=data.get('accent','')
    if accent not in ('','pink','yellow','green','blue','orange','lilac','mint','red'): raise APIError('Invalid colour.')
    out['accent']=accent
    return out

UPDATES_LOCK=threading.Lock()
BOOKING_LOCK=threading.Lock(); DELEGATED={}
UPDATE_KINDS=('news','feature','policy','notice','tip','event')
MAX_UPDATE_FILES=10*1024*1024
# Shown in Dejoiy Updates until the Dejoiy team posts or deletes anything there.
DEFAULT_UPDATES=json.loads((Path(__file__).with_name('default-updates.json')).read_text(encoding='utf-8'))
# People photos on the default posts (Unsplash License). Only these can be fetched: the server is not an open proxy.
def b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
def shine_token(secret, email, name, admin='', photo='', now=None, ttl=120):
    """Short-lived sign-in token for Shine (Dejoiy's chat app). Shine checks the HMAC with the same
    secret (src/convex/lib/dejoiyMailToken.ts there) and signs the same mailbox user in.
    admin: 'platform' (Zimbra global admin), 'company' (company admin) or '' - Shine takes its admin roles from this.
    photo: the mailbox's profile photo URL here (or ''), which Shine shows as the person's picture."""
    claims={'e':email.lower(),'n':name or '','a':admin,'p':photo,'x':int(((now or time.time())+ttl)*1000),'d':secrets.token_urlsafe(9)}
    body=b64u(json.dumps(claims,separators=(',',':')).encode())
    return body+'.'+b64u(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
def joi_app_token(secret, app='mail', minutes=12*60, now=None):
    """Joi checks this with the app's secret from her admin page (app id 'mail'): it lets her use
    DEJOIY's internal memory inside Dejoiy Mail. Same format as Joi's own signAppToken."""
    body=b64u(json.dumps({'app':app,'exp':int(((now or time.time())+minutes*60)*1000)},separators=(',',':')).encode())
    return body+'.'+b64u(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
def joi_signed(secret, claims):
    body=b64u(json.dumps(claims,separators=(',',':')).encode())
    return body+'.'+b64u(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
def joi_read(secret, token, kind, max_seconds):
    """Claims of a token Joi (or this server) signed with the shared mail-app secret, or None.
    kind keeps a login token from being used as a mailbox token and the other way round."""
    if not secret or not isinstance(token,str) or token.count('.')!=1: return None
    body,mac=token.split('.')
    if not hmac.compare_digest(mac,b64u(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())): return None
    try: c=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
    except Exception: return None
    now=time.time()*1000
    if not isinstance(c,dict) or c.get('app')!='mail' or c.get('k')!=kind or not isinstance(c.get('exp'),(int,float)) or not now<c['exp']<now+max_seconds*1000: return None
    return c
JOI_GRANT_SECONDS=12*3600
def joi_grant_key(directory=None):
    """The key for Joi's mailbox grants. Only this server has it (Joi does not), so Joi cannot
    make a grant for a mailbox whose owner never opened her from here. Kept beside the sessions."""
    if not directory: return secrets.token_hex(32)
    path=Path(directory)/'joi-grant.key'
    try: return path.read_text().strip()
    except FileNotFoundError: pass
    key=secrets.token_hex(32)
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f: f.write(key)
    return key
def joi_grant_ok(claims, grant, sessions, now=None):
    """Joi's mailbox request (claims) is allowed only for the person a live grant names:
    same mailbox, and that person's sign-in here (which made the grant) is still open."""
    if not claims or not grant or str(claims.get('e','')).lower()!=str(grant.get('e','')).lower(): return False
    now=now or time.time()
    for sid in list(sessions):
        try: s=sessions[sid]
        except KeyError: continue
        if s.get('joi_grant') and hmac.compare_digest(str(s['joi_grant']),str(grant.get('g',''))):
            return s.get('expires',0)>now and str(s.get('user',{}).get('email','')).lower()==str(grant['e']).lower()
    return False
def shine_admin(user):
    return 'platform' if user.get('canManageRoles') is True else 'company' if user.get('isAdmin') is True else ''
def safe_return(raw, fallback='/app/chats'):
    return raw if raw and raw.startswith('/') and not raw.startswith('//') and len(raw)<500 and not any(ord(c)<33 for c in raw) else fallback
ANDROID_APPS=json.loads((Path(__file__).with_name('android-apps.json')).read_text(encoding='utf-8'))
def assetlinks(app):
    """Digital Asset Links: proves the Play Store app and this site belong together, so the app opens
    the site full screen with no browser bar. Fingerprints come from android-apps.json or the environment."""
    entry=ANDROID_APPS.get(app,{}); extra=os.environ.get('DMAIL_ADMIN_ANDROID_SHA256' if app=='admin' else 'DMAIL_ANDROID_SHA256','')
    prints=[f.strip().upper() for f in [*entry.get('sha256',[]),*extra.split(',')] if re.fullmatch(r'([0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}',f.strip())]
    if not prints: return []
    return [{'relation':['delegate_permission/common.handle_all_urls'],'target':{'namespace':'android_app','package_name':entry['package'],'sha256_cert_fingerprints':prints}}]
UPDATE_PHOTOS={p['photo']['id']:p['photo']['src'] for p in DEFAULT_UPDATES if p.get('photo')}
SEED_UPDATE_IDS=[p['id'] for p in DEFAULT_UPDATES if p.get('seed')]
def dejoiy_posts(saved):
    """Saved Dejoiy Updates, plus any new launch post from default-updates.json ("seed": true) that the
    team hasn't seen yet. Once the team posts, pins or deletes, those posts count as seen, so a deleted one stays gone."""
    if 'posts' not in saved: return [dict(p) for p in DEFAULT_UPDATES]
    seen=set(saved.get('seen',[])); ids={p.get('id') for p in saved['posts']}
    fresh=[dict(p) for p in DEFAULT_UPDATES if p.get('seed') and p['id'] not in seen and p['id'] not in ids]
    rest=[{**p,'pinned':False} for p in saved['posts']] if any(p.get('pinned') for p in fresh) else saved['posts']
    return fresh+rest
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

class AuditLog:
    """What happened, for the admin's Reports page: sign-ins, mail sent from the web app, admin changes.
    Never passwords or mail content: only who, what kind, which address it touched, from where, when.
    Kept 90 days."""
    KEEP=90*86400
    def __init__(self, path=None):
        self.lock=threading.Lock()
        self.db=sqlite3.connect(path or ':memory:', check_same_thread=False, timeout=10)
        if path: os.chmod(path, 0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS events (ts REAL, kind TEXT, actor TEXT, domain TEXT, target TEXT, ip TEXT, n INTEGER)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_ts ON events (ts)'); self.db.commit()
    def add(self, kind, actor, target='', ip='', n=1, now=None):
        actor=str(actor or '').lower()[:320]; now=now or time.time()
        try:
            with self.lock:
                self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',(now,kind,actor,actor.rsplit('@',1)[-1] if '@' in actor else '',str(target or '')[:320],str(ip or '')[:45],int(n)))
                self.db.execute('DELETE FROM events WHERE ts<?',(now-self.KEEP,)); self.db.commit()
        except sqlite3.Error: pass  # the log must never break sign-in or sending
    def failures(self, scope=None, days=14, now=None):
        """Web sends the mail server refused (kept in Drafts), for the Undelivered mail page."""
        now=now or time.time(); where,args=('AND domain=?',(scope,)) if scope else ('',())
        with self.lock:
            rows=self.db.execute(f'SELECT ts,actor,target FROM events WHERE kind=? AND ts>=? {where} ORDER BY ts DESC LIMIT 500',
                                 (SEND_FAILED_KIND,now-days*86400,*args)).fetchall()
        out=[]
        for ts,actor,target in rows:
            code,_,to=str(target or '').partition('|')
            out.append({'ts':ts,'from':actor,'to':to,'code':code})
        return out
    def report(self, scope=None, days=14, now=None):
        """Numbers for the last `days` days and the newest events; a company admin (scope) sees only its own domain."""
        now=now or time.time(); since=now-days*86400; where,args=('AND domain=?',(scope,)) if scope else ('',())
        with self.lock:
            rows=self.db.execute(f'SELECT ts,kind,actor,target,ip,n FROM events WHERE ts>=? {where} ORDER BY ts DESC',(since,*args)).fetchall()
        day=lambda ts: time.strftime('%Y-%m-%d',time.gmtime(ts))
        series={day(now-i*86400):{'sent':0,'signins':0,'failed':0,'active':set()} for i in range(days-1,-1,-1)}
        senders={}; failed={}
        for ts,kind,actor,target,ip,n in rows:
            d=series.get(day(ts))
            if d is None: continue
            if kind=='send': d['sent']+=n; senders[actor]=senders.get(actor,0)+n; d['active'].add(actor)
            elif kind=='signin': d['signins']+=1; d['active'].add(actor)
            elif kind=='signin_failed': d['failed']+=1; failed[actor]=failed.get(actor,0)+1
        top=lambda m: [{'email':k,'count':v} for k,v in sorted(m.items(),key=lambda x:-x[1])[:5]]
        event=lambda r: {'at':int(r[0]*1000),'kind':r[1],'actor':r[2],'target':r[3],'ip':r[4],'count':r[5]}
        return {'days':[{'date':k,'sent':v['sent'],'signins':v['signins'],'failed':v['failed'],'active':len(v['active'])} for k,v in series.items()],
            'totals':{'sent':sum(v['sent'] for v in series.values()),'signins':sum(v['signins'] for v in series.values()),'failed':sum(v['failed'] for v in series.values()),
                'active':len(set().union(*[v['active'] for v in series.values()]))},
            'topSenders':top(senders),'failedSignins':top(failed),
            'signins':[event(r) for r in rows if r[1] in ('signin','signin_failed')][:60],
            'audit':[event(r) for r in rows if r[1].startswith(('admin','api:','automation:'))][:100]}

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
    """Profile photos keyed by mailbox address. Everyone signed in to Dejoiy Mail sees everyone's photo, on every
    domain, and Shine shows the same photo (no BIMI needed: these are our own mailboxes)."""
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
    def versions(self):
        with self.lock:
            if self.db is None: return {r[0]:r[4] for r in self.memory.values()}
            return {email:version for email,version in self.db.execute('SELECT email,version FROM avatars')}
    def version(self, email):
        return self.versions().get(email.lower())

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

AUTOMATION_OPS=('automations_get','automation_save')
WEBHOOK_OPS=('webhooks_get','webhook_add','webhook_remove','webhook_set_active','webhook_test')
APITOKEN_OPS=('apitokens_get','apitoken_add','apitoken_revoke')
# the automation API: (method, path) -> the token permission it needs
API_ROUTES={('POST','/api/v1/mail/send'):'mail.send',('POST','/api/v1/mail/label'):'mail.label',
    ('GET','/api/v1/mail/messages'):'mail.read',('POST','/api/v1/shine/post'):'shine.post'}
MAX_API_BYTES=1024*1024


def webhook_domain(scope, chosen):
    """Whose webhooks: a company admin only ever their own domain (never taken from the request);
    a platform admin the domain they chose."""
    if scope: return scope.lower()
    domain=str(chosen or '').strip().lower()
    if not DOMAIN_NAME.fullmatch(domain): raise APIError('Choose a domain first.')
    return domain


def shown_mb(raw):
    """A size limit stored in bytes, as the whole MB the Settings card shows (10240000 -> 10)."""
    try: return round(int(raw or 0)/1048576)
    except ValueError: return 0


def size_limit_changes(current, wanted):
    """The size limits to write: only those whose shown MB was changed, so saving the Settings card
    never rewrites a limit nobody touched (a stored 10240000 shows as 10 and stays 10240000)."""
    return [(name, str(mb*1048576)) for name, mb in wanted.items() if mb != shown_mb(current.get(name))]


ADMIN_ASSETS = {'/admin.html','/js/admin-app.js','/js/admin-console.js','/css/admin.css'}
# the console's own pages: /admin/monitor/mail-queues, /admin/manage/accounts/<id>, /admin/search ...
ADMIN_PAGE = re.compile(r'/admin/[a-z0-9-]+(?:/[a-zA-Z0-9.-]{1,253}){0,3}')
DOMAIN_NAME = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')
LOCAL_PART = re.compile(r'[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?')
FREE_MAIL = {'gmail.com','googlemail.com','yahoo.com','yahoo.co.in','outlook.com','hotmail.com','live.com','msn.com','icloud.com','me.com',
    'aol.com','proton.me','protonmail.com','zoho.com','zohomail.in','yandex.com','gmx.com','mail.com','rediffmail.com'}
SIGNUP_TTL = 7*24*3600

def dns_lookup(name, kind='TXT'):
    """Public DNS answers via DNS-over-HTTPS, so checks match what the internet sees."""
    code={'TXT':16,'MX':15,'A':1,'CNAME':5}[kind]
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

# ---------- sender logos (BIMI): the brand logo a domain publishes for its own mail ----------
def verified_sender(results, sender, authserv):
    """The sender's domain when OUR mail server checked the message and DMARC passed for that very domain, else ''.
    Only Authentication-Results stamped by our own server count (a sender can write anything into its own headers)."""
    domain=sender.rsplit('@',1)[-1].lower() if '@' in sender else ''
    if not domain: return ''
    for value in results:
        text=re.sub(r'\s+',' ',str(value or '')).strip().lower()
        if text.split(';',1)[0].strip().split(' ')[0]!=str(authserv).lower(): continue
        if not re.search(r'(^|[;\s])dmarc=pass\b',text): continue
        named=re.search(r'header\.from=([a-z0-9.-]+)',text)
        if named is None or named.group(1)==domain: return domain
    return ''
BIMI_UNSAFE=re.compile(rb'<\s*(script|foreignobject|iframe|image|use|a)\b|\bon[a-z]+\s*=|(xlink:)?href\s*=|javascript:|<!entity|<!doctype',re.I)
def bimi_record(domain, lookup=None):
    """The logo link a domain publishes (default._bimi TXT, v=BIMI1; l=https://…svg), only when its DMARC policy
    is enforced (p=quarantine or p=reject), as the BIMI standard requires. '' when there is none."""
    lookup=lookup or dns_lookup
    policy=next((t for t in lookup('_dmarc.'+domain) if t.lower().startswith('v=dmarc1')),'')
    if not re.search(r'\bp\s*=\s*(quarantine|reject)\b',policy,re.I): return ''
    record=next((t for t in lookup('default._bimi.'+domain) if t.lower().startswith('v=bimi1')),'')
    link=re.search(r'\bl\s*=\s*(https://[^\s;"<>]{4,300})',record,re.I)
    return link.group(1) if link else ''
def public_host(host):
    """True when every address of this host is on the public internet (never fetch from inside our own network)."""
    try: found={info[4][0] for info in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
    except OSError: return False
    return bool(found) and all(ipaddress.ip_address(a.split('%')[0]).is_global for a in found)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None
def fetch_bimi_logo(url, limit=131072):
    """The SVG behind a BIMI link, or None. Public https only, no redirects, small, and nothing active inside it."""
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.port not in (None,443) or parsed.username or not public_host(parsed.hostname): return None
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,headers={'User-Agent':'DejoiyMail-BIMI/1.0','Accept':'image/svg+xml'}),timeout=6) as response:
            raw=response.read(limit+1)
    except (OSError,ValueError): return None
    return raw if clean_bimi_svg(raw,limit) else None
def clean_bimi_svg(raw, limit=131072):
    """A BIMI logo is a plain picture: an <svg> with no scripts, links, embedded pages or outside references."""
    return 0<len(raw)<=limit and b'<svg' in raw[:2048].lower() and not BIMI_UNSAFE.search(raw)

# ---------- a company's own sign-in address (mail.theircompany.com) ----------
LOGIN_HOST=re.compile(r'(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){2,}[a-z]{2,63}')
def clean_login_host(raw, mail_host, own_domain):
    """A sign-in address a company may use: a subdomain of its OWN mail domain (mail.acme.in for acme.in),
    never an IP, never ours. Tying it to their domain means nobody can claim someone else's name."""
    host=str(raw or '').strip().lower().rstrip('.')
    if host.startswith(('http://','https://')) or '/' in host: raise APIError('Enter only the address, like mail.yourcompany.com.')
    if not LOGIN_HOST.fullmatch(host): raise APIError('Enter a subdomain, like mail.yourcompany.com.')
    base='.'.join(str(mail_host).lower().split('.')[-2:])
    if host==str(mail_host).lower() or host.endswith('.'+base) or host==base: raise APIError('That address belongs to Dejoiy. Use a subdomain of your own domain.')
    if not host.endswith('.'+own_domain.lower()): raise APIError(f'Use a subdomain of {own_domain}, like mail.{own_domain}.')
    return host
def clean_brand(data):
    """What a company may change on its sign-in page: its name, one colour and one line of text. Text only, no HTML."""
    text=lambda v,n: re.sub(r'[\x00-\x1f<>]','',str(v or '')).strip()[:n]
    colour=str(data.get('colour') or '').strip().lower()
    if colour and not re.fullmatch(r'#[0-9a-f]{6}',colour): raise APIError('Pick the colour as #rrggbb, like #1f5ce0.')
    return {'name':text(data.get('name'),60),'tagline':text(data.get('tagline'),120),'colour':colour}
def host_points_here(host, mail_host, lookup=None):
    """True when the address reaches this mail server: a CNAME to it, or the same A records."""
    lookup=lookup or dns_lookup
    if str(mail_host).lower() in lookup(host,'CNAME'): return True
    ours=set(lookup(mail_host,'A')); theirs=set(lookup(host,'A'))
    return bool(theirs) and theirs<=ours

# Outgoing mail to Gmail and other outside domains is relayed through Amazon SES, so SES may send for every domain.
SPF_INCLUDES=[x for x in os.environ.get('SPF_INCLUDES','amazonses.com').replace(',',' ').split() if re.fullmatch(r'[a-z0-9.-]+',x)]
def merged_spf(existing, mail_host):
    """One SPF record per domain is allowed, so ours is merged into the one already published."""
    terms=[t for t in (existing or 'v=spf1').split()[1:] if not re.fullmatch(r'[~?+-]?all',t,re.I)]
    ending=next((t for t in (existing or '').split() if re.fullmatch(r'[~?+-]?all',t,re.I)),'~all')
    for want in ('mx','a:'+mail_host,*('include:'+x for x in SPF_INCLUDES)):
        if want not in terms: terms.append(want)
    return ' '.join(['v=spf1',*terms,ending])

def domain_records(domain, mail_host, dkim_dir, bimi_logo=''):
    """The DNS records a hosted domain needs, each with its public status: ok, missing or conflict."""
    dkim=None
    if dkim_dir:
        try: dkim=json.loads((Path(dkim_dir)/(domain+'.json')).read_text())
        except (OSError,ValueError): dkim=None
    txt=dns_lookup(domain); mx=dns_lookup(domain,'MX')
    def record(kind,rtype,host,value,ok,found=(),note='',**extra):
        status='ok' if ok and not note else 'conflict' if note else 'missing'
        return {'kind':kind,'type':rtype,'host':host,'value':value,'ok':status=='ok','status':status,'found':list(found),'note':note,**extra}
    others=[h for h in mx if h!=mail_host]
    records=[record('MX','MX','@',mail_host,mail_host in mx,mx,
        f"Delete the other MX records ({', '.join(others)}), or some mail will keep going to the old provider." if mail_host in mx and others
        else f"Replace the current MX records ({', '.join(others)}) with this one." if others else '',priority=10,purpose='Receives mail for your domain')]
    spf=[t for t in txt if t.lower().startswith('v=spf1')]
    spf_ok=len(spf)==1 and (mail_host in spf[0] or ' mx' in spf[0]) and all('include:'+x in spf[0] for x in SPF_INCLUDES)
    records.append(record('SPF','TXT','@',merged_spf(spf[0] if len(spf)==1 else '',mail_host),spf_ok,spf,
        'A domain may have only one SPF record. Delete the extra ones and keep only the value shown.' if len(spf)>1
        else 'Your domain already has an SPF record. Edit it to the value shown instead of adding a second one.' if spf and not spf_ok else '',
        purpose='Allows Dejoiy Mail to send for your domain'))
    if dkim:
        live=[t for t in dns_lookup(dkim['host']+'.'+domain) if t.startswith('v=DKIM1')]
        records.append(record('DKIM','TXT',dkim['host'],dkim['value'],dkim['value'].replace(' ','') in [t.replace(' ','') for t in live],live,
            'A different key is published here. Replace it with the value shown.' if live and dkim['value'].replace(' ','') not in [t.replace(' ','') for t in live] else '',
            purpose='Signs every message so it cannot be forged'))
    else: records.append({'kind':'DKIM','type':'TXT','host':'','value':'','ok':False,'status':'pending','found':[],'note':'','pending':True,'purpose':'Signs every message so it cannot be forged'})
    dmarc=[t for t in dns_lookup('_dmarc.'+domain) if t.startswith('v=DMARC1')]
    enforced=len(dmarc)==1 and bool(re.search(r'\bp\s*=\s*(quarantine|reject)\b',dmarc[0],re.I))
    records.append(record('DMARC','TXT','_dmarc',f'v=DMARC1; p=quarantine; rua=mailto:postmaster@{domain}',len(dmarc)==1,dmarc,
        'Only one DMARC record is allowed. Delete the extra ones.' if len(dmarc)>1 else '',
        purpose='Tells Gmail and Outlook what to do with forged mail'))
    # p=none still delivers mail, so it stays "ok"; the note is advice, not a fault
    if len(dmarc)==1 and not enforced: records[-1]['note']='Your DMARC record only watches (p=none), so forged mail still gets through and your logo cannot show. Change it to the value shown.'
    if bimi_logo:
        live=[t for t in dns_lookup('default._bimi.'+domain) if t.lower().startswith('v=bimi1')]
        value=f'v=BIMI1; l={bimi_logo};'
        records.append(record('BIMI','TXT','default._bimi',value,enforced and any(bimi_logo in t for t in live),live,
            '' if enforced or not live else 'The logo only shows once DMARC above is p=quarantine or p=reject.',
            purpose='Shows your logo beside your mail in Yahoo, Apple Mail, Dejoiy Mail and others (Gmail also needs a paid mark certificate)'))
    return records

def signup_records(pending, mail_host, dkim_dir):
    """Everything a new company adds at once: the ownership proof first, then the records that make mail flow."""
    proof={'kind':'Verification','type':'TXT','host':'@','value':pending['code'],'purpose':'Proves you own the domain'}
    try: rest=domain_records(pending['domain'],mail_host,dkim_dir)
    except APIError: rest=[]
    return [proof,*rest]

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

def delegated_token(provisioner, email):
    """A one-hour mailbox token for this address, issued by the service admin (cached until it nears its end)."""
    cached=DELEGATED.get(email)
    if cached and cached[1]>time.time()+60: return cached[0]
    r=node(ADMIN,'DelegateAuthRequest',{'duration':'3600'}); r.append(node(ADMIN,'account',{'by':'name'},email))
    token=provisioner.admin.call(r,provisioner.token()).findtext('{'+ADMIN+'}authToken')
    if not token: raise APIError('Booking is unavailable right now.',502)
    DELEGATED[email]=(token,time.time()+3600); return token
def inbox_heads(zimbra, token):
    """The newest inbox mail as headers only (id, date in ms, sender, subject): what the new-mail watcher compares.
    Webhook notes never carry the subject; only an automation whose admin switched it on shows it."""
    r=node(MAIL,'SearchRequest',{'types':'message','limit':'20','sortBy':'dateDesc'}); r.append(node(MAIL,'query',text='in:inbox'))
    out=[]
    for m in zimbra.call(r,token).findall('{'+MAIL+'}m'):
        sender=next((e.get('a','') for e in m.findall('{'+MAIL+'}e') if e.get('t')=='f'),'')
        su=m.find('{'+MAIL+'}su')
        try: out.append({'id':m.get('id'),'date':int(m.get('d') or 0),'from':sender,'subject':(su.text or '') if su is not None else ''})
        except ValueError: pass
    return out
def shine_admin_call(site, secret, payload, timeout=15):
    """Shine's admin endpoint (shared secret); its own refusals come back as readable errors."""
    if not secret: raise APIError("Shine isn't connected to this mail server yet.",503)
    request=urllib.request.Request(site+'/dejoiy/admin',data=json.dumps(payload).encode(),method='POST',
        headers={'Content-Type':'application/json','Authorization':'Bearer '+secret})
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response: return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code==400:
            try: raise APIError(str(json.loads(error.read()).get('error') or "Shine couldn't do that.")[:200])
            except ValueError: pass
        if error.code==404: raise APIError('Shine needs its latest update before it can be managed from here.',502)
        raise APIError('Shine is not reachable right now.',502)
    except (urllib.error.URLError,TimeoutError,ValueError): raise APIError('Shine is not reachable right now.',502)
class FollowupMail:
    """What the follow-up reminder needs from the mail server, acting for each mailbox with a one-hour delegated token."""
    def __init__(self, zimbra, provisioner, sender):
        self.zimbra, self.provisioner, self.sender = zimbra, provisioner, sender
    def token(self, email): return delegated_token(self.provisioner, email)
    def mailboxes(self, domain): return domain_mailboxes(self.provisioner, domain)
    def sent(self, email, since_ms):
        """Sent mail since then (newest 100): id, conversation, date (ms), recipients, subject."""
        r=node(MAIL,'SearchRequest',{'types':'message','limit':'100','sortBy':'dateDesc','recip':'2'}); r.append(node(MAIL,'query',text='in:sent'))
        out=[]
        for m in self.zimbra.call(r,self.token(email)).findall('{'+MAIL+'}m'):
            try: date=int(m.get('d') or 0)
            except ValueError: continue
            if date<since_ms: break
            su=m.find('{'+MAIL+'}su')
            out.append({'id':m.get('id'),'cid':m.get('cid') or '','date':date,'subject':(su.text or '') if su is not None else '',
                'to':[e.get('a','') for e in m.findall('{'+MAIL+'}e') if e.get('t') in ('t','c')]})
        return out
    def replied(self, email, mail):
        """True when anyone but the sender wrote in that conversation after the mail went out."""
        if not mail.get('cid') or str(mail['cid']).startswith('-'): return False   # a lone mail: Zimbra makes a conversation once a reply comes
        r=node(MAIL,'GetConvRequest'); r.append(node(MAIL,'c',{'id':str(mail['cid'])}))
        for m in self.zimbra.call(r,self.token(email)).iter('{'+MAIL+'}m'):
            sender=next((e.get('a','') for e in m.findall('{'+MAIL+'}e') if e.get('t')=='f'),'')
            if int(m.get('d') or 0)>mail['date'] and sender.lower()!=email.lower(): return True
        return False
    def remind(self, email, subject, text):
        """The reminder goes straight into the person's own inbox, unread (never through the internet)."""
        from email.message import EmailMessage
        from email.utils import formatdate, make_msgid
        msg=EmailMessage(); msg['From']=f'Dejoiy Mail <{self.sender}>'; msg['To']=email; msg['Subject']=subject
        msg['Date']=formatdate(localtime=True); msg['Message-ID']=make_msgid(domain=self.sender.rsplit('@',1)[1]); msg.set_content(text)
        r=node(MAIL,'AddMsgRequest'); m=node(MAIL,'m',{'l':FOLDERS['inbox'],'f':'u'}); m.append(node(MAIL,'content',text=msg.as_string())); r.append(m)
        self.zimbra.call(r,self.token(email))
def domain_mailboxes(provisioner, domain):
    """Every person's address in one domain (system mailboxes left out)."""
    r=node(ADMIN,'GetAllAccountsRequest'); r.append(node(ADMIN,'domain',{'by':'name'},domain))
    return [a.get('name') for a in provisioner.admin.call(r,provisioner.token()).findall('{'+ADMIN+'}account')
            if a.get('name') and not any(x.get('n')=='zimbraIsSystemResource' and x.text=='TRUE' for x in a.findall('{'+ADMIN+'}a'))]
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

# Business password policy: at least 10 characters, three of lower/upper/digit/symbol, not the mailbox
# name and not a well-known password. Zimbra's own policy (zimbraPasswordMinLength) can only raise it.
PASSWORD_MIN=10
COMMON_PASSWORDS={'password','password1','password123','qwerty123','1234567890','123456789','iloveyou','welcome123','admin12345','letmein123','dejoiy123','dejoiymail'}
def password_problem(new,email=''):
    if not isinstance(new,str) or len(new)>4096: return 'Choose a new password.'
    if len(new)<PASSWORD_MIN: return f'Use at least {PASSWORD_MIN} characters.'
    kinds=sum(bool(re.search(x,new)) for x in (r'[a-z]',r'[A-Z]',r'[0-9]',r'[^A-Za-z0-9]'))
    if kinds<3: return 'Mix at least three of: lowercase, uppercase, numbers and symbols.'
    local=(email or '').split('@')[0].lower()
    parts=[x for x in re.split(r'[^a-z0-9]+',local) if len(x)>=4]
    if new.lower() in COMMON_PASSWORDS or (len(local)>=3 and local in new.lower()) or any(x in new.lower() for x in parts): return 'That password is too easy to guess. Avoid common words and your mailbox name.'
    return ''

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

# A designed mail (newsletter, receipt, Joi's letters) is only readable with its own layout, so received mail keeps a
# small allowlist of inline styles and table attributes. Nothing that loads, runs or leaves its box: no url(), no
# positioning, no negative offsets. Everything else is dropped as before.
STYLE_PROPS={'color','background','background-color','font','font-size','font-weight','font-style','font-family','text-align','text-decoration',
    'text-transform','line-height','letter-spacing','white-space','word-break','vertical-align','padding','margin','border','border-radius',
    'border-collapse','border-spacing','width','max-width','min-width','height','max-height','min-height','display','overflow','opacity','box-sizing','table-layout'}
STYLE_SIDES=re.compile(r'(?:padding|margin|border)-(?:top|right|bottom|left)(?:-(?:color|width|style|radius))?|border-(?:color|width|style|(?:top|bottom)-(?:left|right)-radius)')
STYLE_VALUE=re.compile(r'[a-z0-9#%.,()\'" +/!-]{1,200}')
STYLE_BAD=re.compile(r'url\s*\(|expression|javascript|(?:^|[\s(,])-\s*[\d.]')
DISPLAYS={'none','block','inline','inline-block','table','table-row','table-cell'}
TABLE_ATTRS={'width':r'\d{1,4}%?','height':r'\d{1,4}%?','align':'left|center|right','valign':'top|middle|bottom','bgcolor':r'#[0-9a-f]{3,8}|[a-z]{3,20}',
    'cellpadding':r'\d{1,2}','cellspacing':r'\d{1,2}','border':r'\d','colspan':r'\d{1,2}','rowspan':r'\d{1,2}'}
def safe_style(value):
    """The allowed part of an inline style, or '' when nothing in it is allowed."""
    kept=[]
    for part in str(value or '')[:2000].split(';'):
        name,_,val=part.partition(':'); name=name.strip().lower(); val=' '.join(val.lower().split())
        if not val or not (name in STYLE_PROPS or STYLE_SIDES.fullmatch(name)): continue
        if not STYLE_VALUE.fullmatch(val) or STYLE_BAD.search(val): continue
        if name=='display' and val not in DISPLAYS: continue
        kept.append(name+':'+val)
    return ';'.join(kept)
class SafeHTML(HTMLParser):
    tags={'p','div','span','br','b','strong','i','em','u','s','strike','ul','ol','li','blockquote','pre','code','h1','h2','h3','a','table','tbody','thead','tr','td','th'}
    styled_tags={'h4','h5','h6','hr','center','small','sup','sub','font'}
    def __init__(self, images=None, styled=False):
        super().__init__(); self.parts=[]; self.skip=0; self.stack=[]; self.images=images; self.styled=styled; self.designed=False
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','iframe','object','svg','math','head'):
            self.skip+=1; return
        if self.skip: return
        if tag=='img': return self.image(dict(attrs))
        if tag not in self.tags and not (self.styled and tag in self.styled_tags): return
        safe=''
        if self.styled:
            given=dict(attrs); style=safe_style(given.get('style'))
            if style: safe+=' style="'+html.escape(style,quote=True)+'"'; self.designed=True
            if tag in ('table','tr','td','th'):
                for name,rule in TABLE_ATTRS.items():
                    value=(given.get(name) or '').strip().lower()
                    if value and re.fullmatch(rule,value): safe+=f' {name}="{value}"'
        if tag=='a':
            href=dict(attrs).get('href','').strip()
            if re.match(r'^(?:https?://|mailto:)',href,re.I):
                safe+=' href="'+html.escape(href,quote=True)+'" target="_blank" rel="noopener noreferrer"'
        self.parts.append('<'+tag+safe+'>')
        if tag not in ('br','hr'): self.stack.append(tag)
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

LABEL_TONES=(('important','important','#FF4FA3','Important'),(r'urgent|asap|alert|security|warning|overdue|critical','urgent','#FF5A5F','Urgent'),
    (r'financ|bill|invoice|payment|bank|tax|receipt|salary|money','money','#FF8A3D','Money'),(r'work|project|team|client|office|meeting','work','#FFD23F','Work'),
    (r'personal|family|friend|home','personal','#3DDC84','Personal'),(r'design|creative|idea|social|promo|fun','ideas','#B892FF','Ideas'),
    (r'update|newsletter|digest','updates','#4DA3FF','Updates'))
def label_tone(label):
    """The same colours the inbox uses, so a Work mail looks like Work wherever it lands: (key, colour, name)."""
    for pattern,key,colour,name in LABEL_TONES:
        if label and re.search(pattern,label,re.I): return key,colour,name
    return 'mail','#FF4FA3',''
def email_template(inner, label, app_url):
    """Outgoing mail: an animated :D banner in the label colour, the message, and a Dejoiy Mail footer.
    The banner and logo are images, so dark-mode mail apps cannot recolour them; tables and inline
    styles only, because that is all most mail apps keep."""
    key,colour,name=label_tone(label); app=html.escape(app_url,quote=True)
    own='' if not label or label.lower()==name.lower() else (f'<p style="margin:0 0 14px;font:700 12px/1.4 Arial,Helvetica,sans-serif;'
        f'letter-spacing:.04em;text-transform:uppercase;color:#6B6670">Label · {html.escape(label)}</p>')
    return (f'<div data-dejoiy-mail style="margin:0;padding:20px 10px;background:#F6F3F7">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;margin:0 auto;border-collapse:separate">'
        f'<tr><td style="background:{colour};border:3px solid #121212;border-bottom:0;border-radius:24px 24px 0 0;line-height:0;font-size:0;overflow:hidden">'
        f'<a href="{app}"><img src="{app}/assets/mail/banner-{key}.gif" width="594" alt="{html.escape(name or "Dejoiy Mail")}" '
        f'style="display:block;width:100%;max-width:594px;height:auto;border:0;border-radius:21px 21px 0 0"></a></td></tr>'
        f'<tr><td style="background:#FFFFFF;border:3px solid #121212;border-top:0;border-radius:0 0 24px 24px;padding:26px 28px 30px;'
        f'color:#1D1B20;font:16px/1.6 Arial,Helvetica,sans-serif">{own}{inner}</td></tr>'
        f'<tr><td align="center" style="padding:26px 8px 6px">'
        f'<a href="{app}" style="text-decoration:none"><img src="{app}/assets/mail/footer-logo.png" alt="Dejoiy Mail" width="160" '
        f'style="display:block;width:160px;height:auto;border:0;margin:0 auto 10px"></a>'
        f'<p style="margin:0;font:13px/1.5 Arial,Helvetica,sans-serif;color:#6B6670">This mail is being sent using '
        f'<a href="{app}" style="color:#D6338A;font-weight:700;text-decoration:none">Dejoiy Mail</a></p>'
        f'</td></tr></table></div>')

# Joi's mailboxes send in Joi's own look (the same layout as the mails the Joi server sends).
JOI_MAILBOXES={a.strip().lower() for a in os.environ.get('JOI_MAILBOXES','joi-ai@mail.dejoiy.com').split(',') if a.strip()}
JOI_ASSETS=os.environ.get('JOI_PUBLIC_URL','https://joi-ai.dejoiy.com').rstrip('/')+'/email/'

def joi_template(inner, app_url):
    """Joi peeking out of her round window up top, the message in a cream card, "Love, Joi", and
    Powered by Dejoiy Mail with the little mail logo. Tables and inline styles only."""
    app=html.escape(app_url,quote=True); a=html.escape(JOI_ASSETS,quote=True)
    font="'Bricolage Grotesque','Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    return (f'<div data-dejoiy-mail data-joi style="margin:0;padding:24px 12px;background:#fff1e6">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;margin:0 auto;background:#fffbf7;border:2px solid #121212;border-radius:28px;box-shadow:6px 6px 0 #121212">'
        f'<tr><td style="padding:18px 22px 0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td valign="middle"><div style="font:800 34px/1 {font};color:#121212;letter-spacing:-1px">Joi</div>'
        f'<div style="font:600 13px/1.4 {font};color:#5b5560;padding-top:4px">your buddy from DEJOIY</div></td>'
        f'<td valign="bottom" align="right" width="150"><img src="{a}joi-peek.gif?v=8" width="150" height="140" alt="Joi peeking out to say hi" style="display:block;border:0;width:150px;height:140px"></td>'
        f'</tr></table></td></tr>'
        f'<tr><td style="background:#d4f53c;padding:9px 28px;border-top:2px solid #121212;border-bottom:2px solid #121212;font:700 13px/1.4 {font};color:#121212">Joi is feeling: happy to write to you</td></tr>'
        f'<tr><td style="padding:26px 28px 10px;color:#121212;font:400 16px/1.6 {font}">{inner}'
        f'<p style="margin:18px 0 14px;font:400 16px/1.6 {font};color:#121212">Love,<br><b>Joi</b> &#128153;</p></td></tr>'
        f'<tr><td style="padding:16px 28px 20px;border-top:2px dashed #121212"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td valign="middle" width="52"><a href="{app}"><img src="{a}dmail-logo.gif" width="44" height="44" alt="Dejoiy Mail" style="display:block;border:0"></a></td>'
        f'<td valign="middle" style="font:700 13px/1.4 {font};color:#121212">Powered by <a href="{app}" style="color:#121212;text-decoration:none">Dejoiy Mail</a><br>'
        f'<span style="font-weight:400;color:#5b5560">Dmail &middot; made with love by DEJOIY</span></td></tr></table>'
        f'<p style="margin:12px 0 0;font:400 12px/1.5 {font};color:#5b5560">&#129302; Joi is an AI. It can make mistakes.</p></td></tr>'
        f'</table></div>')

def safe_html(value, images=None, styled=False):
    """Mail HTML made safe to show. styled=True (received mail only) also keeps the allowlisted layout; a mail that
    brings its own design is put on a white sheet (class mail-html), because its colours assume one."""
    parser=SafeHTML(images,styled); parser.feed(value); parser.close()
    out=''.join(parser.parts)+''.join('</'+t+'>' for t in reversed(parser.stack))
    return '<div class="mail-html">'+out+'</div>' if parser.designed else out

def joi_image_rule(joi_url):
    """Matches a picture file on Joi's own site and nothing else (no other host, no path tricks, no query but ?v=)."""
    return re.compile(re.escape(joi_url.rstrip('/'))+r'/(?:[A-Za-z0-9_-]{1,60}/){0,3}[A-Za-z0-9_-]{1,80}\.(?:gif|png|jpe?g|webp)(?:\?v=[A-Za-z0-9._-]{1,20})?')
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
    def call(self, request, token=None, timeout=25):
        envelope=node(SOAP,'Envelope'); header=ET.SubElement(envelope,'{'+SOAP+'}Header')
        context=ET.SubElement(header,'{urn:zimbra}context')
        if token: ET.SubElement(context,'{urn:zimbra}authToken').text=token
        body=ET.SubElement(envelope,'{'+SOAP+'}Body'); body.append(request)
        req=urllib.request.Request(self.url, ET.tostring(envelope), {'Content-Type':'application/soap+xml; charset=utf-8'})
        try:
            with self.opener.open(req, timeout=timeout) as response:
                raw=response.read(8*1024*1024+1)
        except urllib.error.HTTPError as e:
            raw=e.read(65536)
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, ConnectionError):
            # 'transport': we never got an answer, so a send may or may not have gone out
            raise APIError('Mail server is unavailable. Try again later.',502,'transport')
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
                'mail.MESSAGE_TOO_BIG':'The message is larger than the mail server allows. Remove or shrink attachments, or share a link instead.',
                'mail.SEND_PARTIAL_ADDRESS_FAILURE':'Some recipient addresses were rejected, so the message was not sent. Check the recipients.',
                'mail.SEND_FAILURE':'The mail server could not send this message.',
                'mail.TRY_AGAIN':'The mail server is busy. Try again in a minute.',
                'service.TRY_AGAIN':'The mail server is busy. Try again in a minute.',
                'mail.NO_SUCH_MSG':'The draft or original message no longer exists. Copy your text and start a new message.',
                'mail.UPLOAD_REJECTED':'An attachment was rejected by the mail server.',
                'service.INVALID_REQUEST':'The mail server could not accept this message. Check the recipients and attachments.',
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
    joi_images=None  # pictures on Joi's own site (her letters' header and logo), set when the server starts
    app_url='https://mail.dejoiy.com'  # linked from the footer of every message sent
    def own_image(self, src):
        # Only our own hosted signature images are shown; other remote images could track the reader.
        if self.joi_images and self.joi_images.fullmatch(src): return True   # Joi is ours: her letters show their pictures
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
            req=node(MAIL,'GetMsgRequest'); wanted=node(MAIL,'m',{'id':summary.get('id'),'read':'0','html':'1','neuter':'1'}); wanted.append(node(MAIL,'header',{'n':'Authentication-Results'}))
            req.append(wanted)
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
            display=safe_html(rich,images,styled=True) if rich is not None else html.escape(value).replace('\n','<br>')
            flags=m.get('f',''); attachments=[{'name':p.get('filename'),'size':p.get('s',''),'mid':m.get('id'),'part':p.get('part')} for p in m.iter('{'+MAIL+'}mp') if p.get('filename')]
            subject=m.find('{'+MAIL+'}su')
            result.append({'id':m.get('id'),'conversationId':m.get('cid') or m.get('id'),'messageId':m.get('mid') or '', 'inReplyTo':m.get('irt') or '', 'from':{'name':sender.get('p') or sender.get('a','') if sender is not None else '', 'email':sender.get('a','') if sender is not None else ''},'to':[e.get('a','') for e in addresses if e.get('t')=='t'],'cc':[e.get('a','') for e in addresses if e.get('t')=='c'],'replyTo':next((e.get('a','') for e in addresses if e.get('t')=='r'),''),
                'verified':verified_sender([h.text for h in m.findall('{'+MAIL+'}header') if (h.get('n') or '').lower()=='authentication-results'],sender.get('a','') if sender is not None else '',getattr(self,'authserv','') or getattr(self,'mail_host','')),'subject':subject.text or '' if subject is not None else '', 'body':display,'folder':reverse.get(m.get('l'),'other'),'read':'u' not in flags,'starred':'f' in flags,'important':'+' in flags or '!' in flags,'date':int(m.get('d','0')),'labels':[label for label in m.get('tn','').split(',') if label],'hasAttachment':bool(attachments),'attachments':attachments})
        return {'emails':result,'more':more,'limit':50,'offset':offset,'nextOffset':offset+len(out.findall('{'+MAIL+'}m'))}
    def write_message(self, token, data, draft=False, sender=''):
        request=node(MAIL,'SaveDraftRequest' if draft else 'SendMsgRequest')
        attrs={}
        if data.get('id'):
            if not re.fullmatch(r'\d+',str(data['id'])): raise APIError('Invalid draft selection.')
            attrs['id' if draft else 'did']=str(data['id'])
        m=node(MAIL,'m',attrs)
        # Important goes out as high priority, so the recipient's mail app shows it as important too.
        if data.get('important') is True: m.set('f','!')
        label=str(data.get('label') or '').strip()
        if label and (len(label)>64 or ',' in label or any(ord(c)<32 for c in label)): raise APIError('Enter a label of up to 64 characters without commas.')
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
        text,markup=plain(body),safe_html(body,web_image)
        if not draft:
            # Drafts stay plain so the template is added once, when the message actually goes out.
            if sender.lower() in JOI_MAILBOXES:
                text+='\n\nLove,\nJoi\n(Joi is an AI. It can make mistakes.)\n\n--\nPowered by Dejoiy Mail: '+self.app_url
                markup=joi_template(markup,self.app_url)
            else:
                text+='\n\n--\nThis mail is being sent using Dejoiy Mail: '+self.app_url
                markup=email_template(markup,label,self.app_url)
        part=node(MAIL,'mp',{'ct':'text/plain'}); part.append(node(MAIL,'content',text=text)); alternative.append(part)
        part=node(MAIL,'mp',{'ct':'text/html'}); part.append(node(MAIL,'content',text=markup)); alternative.append(part)
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
        request.append(m); out=self.call(request,token,timeout=25 if draft else 60); message=out.find('{'+MAIL+'}m')
        if label and label!='Important' and not draft and message is not None and message.get('id'):
            # The sent copy carries the label; a failed tag never fails a message that already went out.
            try: self.action(token,{'ids':[message.get('id')],'op':'label','label':label})
            except APIError: pass
        return {'id':message.get('id') if message is not None else None,'accepted':not draft,'draftRemoved':bool(not draft and data.get('id'))}
    def sent_copy(self, token, data, since):
        """After a send timed out, look for the copy Zimbra files in Sent once a message is accepted:
        same subject, same To, dated after we started. Found -> it went out; do not send it again."""
        r=node(MAIL,'SearchRequest',{'types':'message','limit':'10','sortBy':'dateDesc','recip':'1'}); r.append(node(MAIL,'query',text='in:sent'))
        want_to={a.strip().lower() for a in re.split(r'[,;\n]+',str(data.get('to',''))) if a.strip()}
        want_su=str(data.get('subject',''))
        for m in self.call(r,token).findall('{'+MAIL+'}m'):
            if int(m.get('d','0'))<since*1000-5000: break
            su=m.find('{'+MAIL+'}su'); to={e.get('a','').lower() for e in m.findall('{'+MAIL+'}e') if e.get('t')=='t'}
            if (su.text if su is not None else '')==want_su and to==want_to: return m.get('id')
        return None
    def upload(self, token, raw, name, mime):
        filename=html.escape(name,quote=True).encode('ascii','xmlcharrefreplace').decode()
        request=urllib.request.Request(self.origin+'/service/upload?fmt=raw,extended',raw,
            {'Content-Type':mime,'Content-Disposition':'attachment; filename="'+filename+'"','Cookie':'ZM_AUTH_TOKEN='+token},method='POST')
        try:
            with self.opener.open(request,timeout=60) as response: value=response.read(65536).decode()
            status=value.split(',',1)[0]
            if status.strip()=='413':
                raise APIError(f'The attachment "{name[:80]}" is larger than the mail server allows. Your message has not been sent.',413,'upload_too_big')
            if status.strip()!='200': raise ValueError()
            _,_,payload=value.split(',',2)
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
    def contacts(self, token, own_domain=''):
        out=self.call(node(MAIL,'GetContactsRequest',{'l':'7','sortBy':'nameAsc'}),token)
        result=[]
        # Divisions come from the address itself: your own company's domain is Work family, the rest Others.
        division=lambda email:'Work family' if own_domain and email.lower().endswith('@'+own_domain) else 'Others'
        for contact in out.findall('{'+MAIL+'}cn'):
            attrs={a.get('n'):a.text or '' for a in contact.findall('{'+MAIL+'}a')}
            if attrs.get('type')=='group': continue
            result.append({'id':contact.get('id'),'name':attrs.get('fullName') or ' '.join(filter(None,[attrs.get('firstName'),attrs.get('lastName')])) or contact.get('fileAsStr') or attrs.get('email',''),
                'email':attrs.get('email',''),'phone':attrs.get('mobilePhone') or attrs.get('workPhone',''),'org':attrs.get('company',''),'presence':'off',
                'division':division(attrs.get('email',''))})
        return {'contacts':result}
    def remember_recipients(self, token, data, own_address=''):
        """Everyone you write to lands in Contacts once; existing contacts are left as they are."""
        wanted={}
        for kind in ('to','cc','bcc'):
            for address in re.split(r'[,;\n]+',str(data.get(kind,''))):
                address=address.strip()
                if EMAIL.fullmatch(address) and address.lower()!=own_address.lower(): wanted.setdefault(address.lower(),address)
        if not wanted: return 0
        known={c['email'].lower() for c in self.contacts(token)['contacts']}
        added=0
        for key,address in list(wanted.items())[:20]:
            if key in known: continue
            name=re.sub(r'[._-]+',' ',address.split('@')[0]).strip().title() or address
            r=node(MAIL,'CreateContactRequest'); contact=node(MAIL,'cn',{'l':'7'})
            for n,v in (('fullName',name),('fileAs','8:'+name),('email',address)): contact.append(node(MAIL,'a',{'n':n},v))
            r.append(contact); self.call(r,token); added+=1
        return added
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
                # the company's mailbox policy can forbid forwarding: checked here, not only hidden in the page
                if key=='forwardTo' and addresses and not self.account_info(token)['features']['forwarding']:
                    raise APIError('Your administrator has turned off forwarding for this mailbox.',403)
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
        limits=attachment_limits(out.get('attSizeLimit'),out.get('docSizeLimit'))
        try: quota=int(attrs.get('zimbraMailQuota') or 0)
        except ValueError: quota=0
        flag=lambda key: attrs.get(key)=='TRUE'
        return {'email':name.text if name is not None else '','used':int(used.text) if used is not None and (used.text or '').isdigit() else 0,'quota':quota,
            'features':{'forwarding':flag('zimbraFeatureMailForwardingEnabled'),'filters':flag('zimbraFeatureFiltersEnabled'),'vacation':flag('zimbraFeatureOutOfOfficeReplyEnabled'),
                'changePassword':flag('zimbraFeatureChangePasswordEnabled'),'pop':flag('zimbraPop3Enabled'),'imap':attrs.get('zimbraImapEnabled')!='FALSE'},
            'limits':limits,
            'passwordMinLength':max(PASSWORD_MIN,int(attrs.get('zimbraPasswordMinLength') or 0) if (attrs.get('zimbraPasswordMinLength') or '0').isdigit() else 0)}
    def change_password(self, token, email, data):
        current=data.get('current'); new=data.get('password')
        if not isinstance(current,str) or not current or len(current)>4096: raise APIError('Enter your current password.')
        problem=password_problem(new,email)
        if problem: raise APIError(problem)
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
    'inboxType':('default','unread','starred','important'),'readingPane':('off','right','bottom'),'autoAdvance':('off','next','previous'),'density':('comfortable','compact'),'starPreset':('one','four','all'),
    'appLook':('clean','colourful'),'phoneBg':('off','on')}
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
        elif key=='notes':
            # the Notepad: plain-text notes kept with the mailbox, so they follow you to every device
            if not isinstance(value,list) or len(value)>200: raise APIError('You can keep up to 200 notes.')
            items=[]
            for n in value:
                if not isinstance(n,dict) or not isinstance(n.get('title',''),str) or not isinstance(n.get('body',''),str): raise APIError('Invalid note.')
                if len(n.get('body',''))>50000: raise APIError('A note can be at most 50000 characters.')
                ident=str(n.get('id',''))[:40]
                ts=n.get('ts',0)
                items.append({'id':ident,'title':n.get('title','')[:200],'body':n.get('body',''),'ts':int(ts) if isinstance(ts,(int,float)) and not isinstance(ts,bool) else 0})
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

DEPARTMENT_MARK='dejoiy:department'
# What a role may do. Console permissions need company-admin access; posting needs none.
PERMISSIONS={'updates.post':'Post in the company box','mailboxes.manage':'Add and edit mailboxes','mailboxes.delete':'Delete mailboxes',
    'teams.manage':'Manage departments and team lists','domain.view':'See the DNS setup','roles.manage':'Manage roles, permissions and the company box'}
CONSOLE_PERMISSIONS=set(PERMISSIONS)-{'updates.post'}
DEFAULT_ROLES=[{'name':'Member','access':'User','perms':[]},{'name':'Team lead','access':'User','perms':['updates.post']},
    {'name':'Department head','access':'User','perms':['updates.post']},{'name':'IT admin','access':'Domain admin','perms':sorted(PERMISSIONS)}]
OP_PERMISSIONS={**{op:'mailboxes.manage' for op in ('create_user','set_name','status','password','quota','forward','add_alias','remove_alias','set_plan')},
    'delete_user':'mailboxes.delete','dns_records':'domain.view',
    **{op:'teams.manage' for op in ('create_department','set_department','create_list','delete_list','add_member','remove_member','list_members')},
    **{op:'roles.manage' for op in ('role','set_title','save_roles','company_settings','policies_get','policies_save','policy_assign')}}
# ---------- mailbox policies a company sets for itself ----------
# Each rule is a real mail-server setting on the mailbox, so the server itself enforces it: (lowest, highest, standard value).
POLICY_NUMBERS={'passwordMinLength':(PASSWORD_MIN,64,PASSWORD_MIN),'passwordMaxAgeDays':(0,365,0),'passwordHistory':(0,24,0),
    'lockoutAfter':(0,20,10),'lockoutMinutes':(5,1440,30),'sessionHours':(1,720,48),'trashDays':(7,365,30),'spamDays':(7,365,30)}
POLICY_SWITCHES={'forwarding':True,'imap':True,'pop':False}
POLICY_MARK='dejoiyPolicy:'
def standard_policy(): return {'name':'Standard','rules':{**{k:v[2] for k,v in POLICY_NUMBERS.items()},**POLICY_SWITCHES}}
def clean_policy(raw):
    """One named policy with every rule present and inside its allowed range (never weaker than Dejoiy's own floor)."""
    if not isinstance(raw,dict): raise APIError('Invalid policy.')
    name=re.sub(r'[\x00-\x1f<>:]','',str(raw.get('name',''))).strip()
    if not 1<=len(name)<=40: raise APIError('Policy names must be 1 to 40 characters.')
    given=raw.get('rules') if isinstance(raw.get('rules'),dict) else {}; rules={}
    for key,(low,high,default) in POLICY_NUMBERS.items():
        value=given.get(key,default)
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high: raise APIError(f'"{name}": {key} must be a whole number from {low} to {high}.')
        rules[key]=value
    if 0<rules['lockoutAfter']<3: raise APIError(f'"{name}": lock a mailbox after at least 3 wrong passwords, or 0 to never lock.')
    for key,default in POLICY_SWITCHES.items():
        value=given.get(key,default)
        if not isinstance(value,bool): raise APIError(f'"{name}": {key} must be on or off.')
        rules[key]=value
    return {'name':name,'rules':rules}
def policy_attrs(policy):
    """The mail-server settings a policy turns into, plus the policy's name on the mailbox."""
    r=policy['rules']; flag=lambda on:'TRUE' if on else 'FALSE'
    out=[('zimbraNotes',POLICY_MARK+policy['name']),('zimbraPasswordMinLength',r['passwordMinLength']),('zimbraPasswordMaxAge',r['passwordMaxAgeDays']),
        ('zimbraPasswordEnforceHistory',r['passwordHistory']),('zimbraPasswordLockoutEnabled',flag(r['lockoutAfter']>0)),
        ('zimbraPasswordLockoutMaxFailures',max(r['lockoutAfter'],1)),('zimbraPasswordLockoutDuration',f"{r['lockoutMinutes']}m"),('zimbraPasswordLockoutFailureLifetime','1h'),
        ('zimbraAuthTokenLifetime',f"{r['sessionHours']}h"),('zimbraMailTrashLifetime',f"{r['trashDays']}d"),('zimbraMailSpamLifetime',f"{r['spamDays']}d"),
        ('zimbraFeatureMailForwardingEnabled',flag(r['forwarding'])),('zimbraImapEnabled',flag(r['imap'])),('zimbraPop3Enabled',flag(r['pop']))]
    if not r['forwarding']: out.append(('zimbraPrefMailForwardingAddress',''))  # switching forwarding off also stops mail already being forwarded
    return [(k,str(v)) for k,v in out]

def read_org(notes):
    """Company roles and the company box name live on the domain itself (its notes), so they stay with the mail server."""
    try: data=json.loads(notes or '')
    except ValueError: data=None
    data=data if isinstance(data,dict) else {}
    roles=[]
    for role in data.get('dejoiyRoles') or []:
        if not isinstance(role,dict) or not isinstance(role.get('name'),str): continue
        access='Domain admin' if role.get('access')=='Domain admin' else 'User'
        # Roles saved before permissions existed: company admins could do everything, members nothing.
        perms=role.get('perms') if isinstance(role.get('perms'),list) else (sorted(PERMISSIONS) if access=='Domain admin' else [])
        roles.append({'name':role['name'],'access':access,'perms':sorted({p for p in perms if p in PERMISSIONS and (access=='Domain admin' or p not in CONSOLE_PERMISSIONS)})})
    box=data.get('companyBox') if isinstance(data.get('companyBox'),str) else ''
    policies=[]
    for raw in data.get('mailPolicies') or []:
        try: policies.append(clean_policy(raw))
        except APIError: continue
    policies=policies or [standard_policy()]
    default=data.get('defaultPolicy') if any(p['name']==data.get('defaultPolicy') for p in policies) else policies[0]['name']
    return {'roles':roles or [dict(r,perms=list(r['perms'])) for r in DEFAULT_ROLES],'boxName':box,'policies':policies,'defaultPolicy':default}
def read_roles(notes): return read_org(notes)['roles']
def write_org(notes, **changes):
    current=read_org(notes); current.update(changes)
    return json.dumps({'dejoiyRoles':current['roles'],'companyBox':current['boxName'],'mailPolicies':current['policies'],'defaultPolicy':current['defaultPolicy']},separators=(',',':'))
def role_perms(roles, title, is_admin):
    """A person's permissions: their role's, or everything for a company admin without a role (the owner)."""
    role=next((r for r in roles if title and r['name'].lower()==title.lower()),None)
    if role is None: return set(PERMISSIONS) if is_admin else set()
    return set(role['perms'])
def attr(element, name):
    return next((a.text or '' for a in element.findall('{'+ADMIN+'}a') if a.get('n')==name),'')

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
    def actor_perms(self, token, actor, scope):
        """None for platform admins (no limits); otherwise the company admin's role permissions."""
        if not scope: return None
        lookup=node(ADMIN,'GetAccountRequest'); lookup.append(node(ADMIN,'account',{'by':'name'},actor))
        account=self.call(lookup,token).find('{'+ADMIN+'}account')
        domain=node(ADMIN,'GetDomainRequest'); domain.append(node(ADMIN,'domain',{'by':'name'},scope))
        found=self.call(domain,token).find('{'+ADMIN+'}domain')
        return role_perms(read_roles(attr(found,'zimbraNotes') if found is not None else ''),attr(account,'title') if account is not None else '',True)
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
                'quota':a.get('zimbraMailQuota','0'),'department':a.get('ou',''),'title':a.get('title','')})
        def optional(build):
            try: return build()
            except APIError: return None
        usage=optional(lambda:{a.get('id'):(int(a.get('used','0')),int(a.get('limit','0'))) for a in self.call(node(ADMIN,'GetQuotaUsageRequest',{'allServers':'1',**({'domain':scope} if scope else {})}),token).findall('{'+ADMIN+'}account')}) or {}
        for account,element in zip(accounts,[x for x in users.findall('{'+ADMIN+'}account') if attributes(x).get('zimbraIsSystemResource')!='TRUE']):
            a=attributes(element)
            account.update({'cosId':a.get('zimbraCOSId',''),'forward':a.get('zimbraPrefMailForwardingAddress',''),
                'keepCopy':a.get('zimbraPrefMailLocalDeliveryDisabled')!='TRUE','lastLogin':a.get('zimbraLastLogonTimestamp',''),
                'policy':(a.get('zimbraNotes') or '')[len(POLICY_MARK):] if (a.get('zimbraNotes') or '').startswith(POLICY_MARK) else '','created':a.get('zimbraCreateTimestamp',''),'used':usage.get(account['id'],(None,None))[0],'limit':usage.get(account['id'],(None,None))[1]})
        def plans():
            return [{'id':c.get('id'),'name':c.get('name'),**cos_fields(attributes(c))} for c in self.call(node(ADMIN,'GetAllCosRequest'),token).findall('{'+ADMIN+'}cos')]
        def lists():
            return [{'id':d.get('id'),'email':d.get('name'),'name':attributes(d).get('displayName',''),
                'department':attributes(d).get('zimbraNotes','')==DEPARTMENT_MARK} for d in self.call(in_domain(node(ADMIN,'GetAllDistributionListsRequest')),token).findall('{'+ADMIN+'}dl')]
        def services():
            # Internal component names never leave the server; the panel shows product-neutral labels.
            return [{'server':x.get('server'),'service':SERVICE_LABELS.get(x.get('service'),'Mail service component'),'running':(x.text or '').strip()=='1'} for x in self.call(node(ADMIN,'GetServiceStatusRequest'),token).findall('.//{'+ADMIN+'}status')]
        def settings():
            config=self.call(node(ADMIN,'GetAllConfigRequest'),token)
            a=attributes(config)
            return {'maxMessageMB':shown_mb(a.get('zimbraMtaMaxMessageSize')),'uploadMaxMB':shown_mb(a.get('zimbraFileUploadMaxSize')),
                'blockedExtensions':sorted({v.text for v in config.findall('{'+ADMIN+'}a') if v.get('n')=='zimbraMtaBlockedExtension' and v.text})}
        every=optional(lists)
        return {'users':accounts,'domains':[{'id':d.get('id'),'domain':d.get('name'),
            'status':attributes(d).get('zimbraDomainStatus','active'),'roles':read_roles(attributes(d).get('zimbraNotes','')),
            'boxName':read_org(attributes(d).get('zimbraNotes',''))['boxName'],'company':attributes(d).get('description','')}
            for d in domains.findall('{'+ADMIN+'}domain')],
            'departments':None if every is None else [x for x in every if x['department']],
            'plans':None if scope else optional(plans),'lists':None if every is None else [x for x in every if not x['department']],'services':None if scope else optional(services),
            'settings':None if scope else optional(settings),'scope':scope}
    def action(self, token, data, actor, scope=None, elevate=None, perms=None):
        """elevate() returns a service-admin token for the few admin-flag changes a company admin may
        request but cannot make with its own rights; it is used only after the target was checked in scope.
        perms limits a company admin to what their role allows (None: no role limits)."""
        op=data.get('op')
        need=OP_PERMISSIONS.get(op)
        if scope and perms is not None and need and need not in perms:
            raise APIError(f'Your role does not allow this. Ask an admin for "{PERMISSIONS[need]}".',403)
        if scope and op in ('create_domain','delete_domain','domain_status','plan_update','set_plan','settings_update'):
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
            problem=password_problem(value,str(data.get('email','')))
            if problem: raise APIError(problem)
            return value
        def company(domain):
            lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'name'},domain))
            found=self.call(lookup,token).find('{'+ADMIN+'}domain')
            if found is None: raise APIError('Domain not found.',404)
            return found,read_org(attr(found,'zimbraNotes'))
        def apply_policy(ident, policy):
            r=node(ADMIN,'ModifyAccountRequest'); r.append(node(ADMIN,'id',text=ident))
            for attr_name,value in policy_attrs(policy): r.append(node(ADMIN,'a',{'n':attr_name},value))
            self.call(r,privileged())
        def domain_accounts(domain):
            request=node(ADMIN,'GetAllAccountsRequest'); request.append(node(ADMIN,'domain',{'by':'name'},domain))
            out=[]
            for account in self.call(request,token).findall('{'+ADMIN+'}account'):
                a={x.get('n'):x.text or '' for x in account.findall('{'+ADMIN+'}a')}
                if a.get('zimbraIsSystemResource')!='TRUE': out.append((account.get('id'),(a.get('zimbraNotes') or '')[len(POLICY_MARK):] if (a.get('zimbraNotes') or '').startswith(POLICY_MARK) else ''))
            return out
        if op in ('policies_get','policies_save'):
            domain=str(data.get('domain','')).strip().lower()
            if not DOMAIN_NAME.fullmatch(domain) or (scope and domain!=scope): raise APIError('You can only change your own company.',403)
            found,org=company(domain)
            if op=='policies_save':
                raw=data.get('policies')
                if not isinstance(raw,list) or not 1<=len(raw)<=20: raise APIError('Keep between 1 and 20 policies.')
                policies=[clean_policy(x) for x in raw]
                if len({p['name'].lower() for p in policies})!=len(policies): raise APIError('Two policies have the same name.')
                default=str(data.get('default',''))
                if not any(p['name']==default for p in policies): raise APIError('Choose which policy new mailboxes get.')
                r=node(ADMIN,'ModifyDomainRequest'); r.append(node(ADMIN,'id',text=found.get('id')))
                r.append(node(ADMIN,'a',{'n':'zimbraNotes'},write_org(attr(found,'zimbraNotes'),policies=policies,defaultPolicy=default)))
                self.call(r,privileged())
                # every mailbox gets its policy's rules again: its own if it still exists, otherwise the default
                by_name={p['name']:p for p in policies}; applied=0; failed=0
                for ident,current in domain_accounts(domain):
                    try: apply_policy(ident,by_name.get(current) or by_name[default]); applied+=1
                    except APIError: failed+=1
                return {'ok':True,'policies':policies,'default':default,'applied':applied,'failed':failed}
            return {'policies':org['policies'],'default':org['defaultPolicy'],'limits':{k:[v[0],v[1]] for k,v in POLICY_NUMBERS.items()}}
        if op=='policy_assign':
            ident=str(data.get('id',''))
            if not re.fullmatch(r'[a-fA-F0-9-]{36}',ident): raise APIError('Invalid mailbox selection.')
            lookup=node(ADMIN,'GetAccountRequest'); lookup.append(node(ADMIN,'account',{'by':'id'},ident))
            account=self.call(lookup,token).find('{'+ADMIN+'}account')
            if account is None: raise APIError('Mailbox not found.',404)
            email=own(account.get('name',''))
            policy=next((p for p in company(email.split('@')[1])[1]['policies'] if p['name']==data.get('policy')),None)
            if not policy: raise APIError('That policy no longer exists.',404)
            apply_policy(ident,policy); return {'ok':True,'policy':policy['name']}
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
            try:  # a new mailbox starts on its company's default policy
                org=company(email.split('@')[1])[1]
                for attr_name,value in policy_attrs(next(p for p in org['policies'] if p['name']==org['defaultPolicy'])):
                    if attr_name!='zimbraPrefMailForwardingAddress': r.append(node(ADMIN,'a',{'n':attr_name},value))
            except APIError: pass
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
                    if targets and attr(account,'zimbraFeatureMailForwardingEnabled')=='FALSE': raise APIError("This mailbox's policy does not allow forwarding. Change its policy first.",403)
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
            # Dejoiy's own domains publish the Dejoiy logo; other companies get this once they can upload their own SVG logo
            logo=getattr(self,'app_url','')+'/assets/brand/bimi-dejoiy.svg' if getattr(self,'app_url','') and (domain=='dejoiy.com' or domain.endswith('.dejoiy.com')) else ''
            return {'domain':domain,'records':domain_records(domain,self.mail_host,self.dkim_dir,logo)}
        elif op=='delete_domain':
            # Platform admins only (checked above). Zimbra refuses a domain that still has mailboxes or lists.
            ident=str(data.get('id',''))
            if not UUID.fullmatch(ident): raise APIError('Invalid domain selection.')
            lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'id'},ident))
            found=self.call(lookup,token).find('{'+ADMIN+'}domain')
            if found is None: raise APIError('Domain not found.',404)
            name=found.get('name','').lower()
            if str(data.get('confirm','')).strip().lower()!=name: raise APIError('Type the domain name to confirm deletion.')
            if actor.lower().endswith('@'+name): raise APIError('You cannot delete the domain your own administrator mailbox is on.')
            try: self.call(node(ADMIN,'DeleteDomainRequest',{'id':ident}),token)
            except APIError as e:
                if 'NOT_EMPTY' in (e.code or '').upper():
                    raise APIError(f'{name} still has mailboxes, aliases or mailing lists. Delete them first, then delete the domain.',409)
                raise
            return {'ok':True,'deleted':name}
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
                own(found.get('name',''))
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
            minimum=whole(data,'passwordMinLength',PASSWORD_MIN,64,f'Minimum password length must be from {PASSWORD_MIN} to 64.')
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
            current={a.get('n'):a.text or '' for a in self.call(node(ADMIN,'GetAllConfigRequest'),token).findall('{'+ADMIN+'}a')}
            for name,value in size_limit_changes(current,{'zimbraMtaMaxMessageSize':size,'zimbraFileUploadMaxSize':upload}): r.append(node(ADMIN,'a',{'n':name},value))
            for x in sorted(set(extensions)) or ['']: r.append(node(ADMIN,'a',{'n':'zimbraMtaBlockedExtension'},x))
        elif op=='create_department':
            # A department is a team list (sales@…) marked as a department; its members are its people.
            name=str(data.get('name','')).strip(); email=str(data.get('email','')).strip().lower()
            if not 1<=len(name)<=64 or any(ord(c)<32 for c in name): raise APIError('Enter a department name of up to 64 characters.')
            if len(email)>320 or not EMAIL.fullmatch(email): raise APIError('Enter the department email address, like sales@yourcompany.com.')
            own(email)
            r=node(ADMIN,'CreateDistributionListRequest'); r.append(node(ADMIN,'name',text=email))
            r.append(node(ADMIN,'a',{'n':'displayName'},name)); r.append(node(ADMIN,'a',{'n':'zimbraNotes'},DEPARTMENT_MARK))
        elif op in ('set_department','set_title'):
            ident=str(data.get('id',''))
            if not UUID.fullmatch(ident): raise APIError('Invalid mailbox selection.')
            lookup=node(ADMIN,'GetAccountRequest'); lookup.append(node(ADMIN,'account',{'by':'id'},ident))
            account=self.call(lookup,token).find('{'+ADMIN+'}account')
            if account is None: raise APIError('Mailbox not found.',404)
            email=own(account.get('name',''))
            r=node(ADMIN,'ModifyAccountRequest'); r.append(node(ADMIN,'id',text=ident))
            if op=='set_title':
                title=str(data.get('title','')).strip()
                if len(title)>64 or any(ord(c)<32 for c in title): raise APIError('Choose a role of up to 64 characters.')
                r.append(node(ADMIN,'a',{'n':'title'},title))
            else:
                target=str(data.get('department',''))
                if target and not UUID.fullmatch(target): raise APIError('Choose a department.')
                found=node(ADMIN,'GetAllDistributionListsRequest'); found.append(node(ADMIN,'domain',{'by':'name'},email.split('@')[1]))
                departments=[d for d in self.call(found,token).findall('{'+ADMIN+'}dl')
                    if any(a.get('n')=='zimbraNotes' and a.text==DEPARTMENT_MARK for a in d.findall('{'+ADMIN+'}a'))]
                chosen=next((d for d in departments if d.get('id')==target),None)
                if target and chosen is None: raise APIError('Department not found.',404)
                # One department per person: leave the others' team lists, join the chosen one.
                for d in departments:
                    member=node(ADMIN,'RemoveDistributionListMemberRequest' if d is not chosen else 'AddDistributionListMemberRequest')
                    member.append(node(ADMIN,'id',text=d.get('id'))); member.append(node(ADMIN,'dlm',text=email))
                    try: self.call(member,token)
                    except APIError: pass  # not a member, or already one
                name=next((a.text or '' for a in chosen.findall('{'+ADMIN+'}a') if a.get('n')=='displayName'),'') if chosen is not None else ''
                r.append(node(ADMIN,'a',{'n':'ou'},name or (chosen.get('name','') if chosen is not None else '')))
        elif op in ('save_roles','company_settings'):
            domain=str(data.get('domain','')).strip().lower()
            if not DOMAIN_NAME.fullmatch(domain) or (scope and domain!=scope): raise APIError('You can only change your own company.',403)
            changes={}
            if op=='save_roles':
                roles=data.get('roles')
                if not isinstance(roles,list) or not 1<=len(roles)<=30: raise APIError('Keep between 1 and 30 roles.')
                clean=[]
                for role in roles:
                    if not isinstance(role,dict): raise APIError('Invalid role.')
                    name=str(role.get('name','')).strip(); access=role.get('access','User'); chosen=role.get('perms',[])
                    if not 1<=len(name)<=40 or any(ord(c)<32 for c in name): raise APIError('Role names must be 1 to 40 characters.')
                    if access not in ('User','Domain admin'): raise APIError('A role can give mail access or company admin access.')
                    if not isinstance(chosen,list) or any(p not in PERMISSIONS for p in chosen): raise APIError('Choose permissions from the list.')
                    if access=='User' and set(chosen)&CONSOLE_PERMISSIONS: raise APIError(f'"{name}" needs company admin access for admin-console permissions.')
                    if any(x['name'].lower()==name.lower() for x in clean): raise APIError(f'"{name}" is listed twice.')
                    clean.append({'name':name,'access':access,'perms':sorted(set(chosen))})
                changes['roles']=clean
            else:
                box=str(data.get('boxName','')).strip()
                if len(box)>40 or any(ord(c)<32 for c in box): raise APIError('The company box name can be up to 40 characters.')
                changes['boxName']=box
            lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'name'},domain))
            found=self.call(lookup,token).find('{'+ADMIN+'}domain')
            if found is None: raise APIError('Domain not found.',404)
            r=node(ADMIN,'ModifyDomainRequest'); r.append(node(ADMIN,'id',text=found.get('id')))
            r.append(node(ADMIN,'a',{'n':'zimbraNotes'},write_org(attr(found,'zimbraNotes'),**changes)))
            self.call(r,privileged()); return {'ok':True,**changes}
        else: raise APIError('Unsupported administration operation.')
        self.call(r,token)
        return {'ok':True}

class Handler(SimpleHTTPRequestHandler):
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.webmanifest':'application/manifest+json','.js':'text/javascript'}
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def log_message(self, *args): pass  # Never log passwords, session IDs or message data.
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','same-origin')
        path=urllib.parse.urlsplit(self.path).path
        if path in ADMIN_ASSETS: self.send_header('Cache-Control','no-store')
        elif not path.startswith('/api/') and (path=='/' or path.endswith(('.html','/sw.js','.webmanifest'))):
            # Pages are re-checked on every visit, so a deploy shows up at once; their CSS/JS carry ?v= and may cache.
            self.send_header('Cache-Control','no-cache')
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
        if self.path.split('?',1)[0].startswith('/api/v1/'): return self.api_v1('GET')
        if self.path=='/.well-known/assetlinks.json':
            app='admin' if self.headers.get('Host','').split(':')[0].lower().startswith('admin-') else 'mail'
            raw=json.dumps(assetlinks(app)).encode(); self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','public, max-age=3600'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if self.path=='/js/runtime-config.js':
            raw=b'window.DEJOIY_LIVE=true;'; self.send_response(200); self.send_header('Content-Type','text/javascript'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw); return
        if self.path.startswith('/api/'):
            try:
                if self.path=='/api/config':
                    custom=self.custom_host()
                    return self.reply(200,{'mode':'live','configured':bool(self.server.zimbra),**({'brand':custom['brand']} if custom else {})})
                # Dejoiy Updates are public news, shown on the home and admin landing pages too. Company boxes never are.
                if self.path=='/api/public/updates':
                    posts=[p for p in dejoiy_posts(self.server.updates.get('dejoiy')) if p.get('audience','both')!='internal']
                    return self.reply(200,{'posts':[{k:p.get(k) for k in ('id','kind','title','body','date','pinned','link','files','photo','art')} for p in posts[:12]]})
                if self.path.startswith('/api/public/photo/'): return self.update_photo(self.path.rsplit('/',1)[1])
                if self.path.startswith('/api/public/avatar?'): return self.public_avatar()
                if self.path.startswith('/api/public/booking/'): return self.reply(200,self.public_booking(self.path.rsplit('/',1)[1]))
                if self.path=='/api/shine/directory': return self.reply(200,self.shine_directory())
                if self.path.startswith('/api/public/update-file?'):
                    return self.update_file(None,urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id',[''])[0])
                sid,s=self.session()
                if self.path=='/api/session':
                    capabilities=self.server.zimbra.capabilities(s['token'])
                    brand=self.brand_for(self.domain(s))  # the company's own name and logo follow its people everywhere
                    return self.reply(200,{'user':{**s['user'],**capabilities},'csrf':s['csrf'],**({'brand':brand} if brand else {})})
                if self.path=='/api/mail': return self.reply(200,self.server.zimbra.messages(s['token']))
                if self.path=='/api/contacts': return self.reply(200,self.server.zimbra.contacts(s['token'],self.domain(s)))
                if self.path=='/api/updates': return self.reply(200,self.updates_view(s))
                if self.path.startswith('/api/calendar?'):
                    q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    try: start,end=int(q.get('start',['0'])[0]),int(q.get('end',['0'])[0])
                    except ValueError: raise APIError('Invalid dates.')
                    return self.reply(200,{'events':self.cal(dcalendar.events,self.server.zimbra,s['token'],start,end)})
                if self.path.startswith('/api/calendar/event?'):
                    ident=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id',[''])[0]
                    return self.reply(200,self.cal(dcalendar.event_detail,self.server.zimbra,s['token'],ident))
                if self.path=='/api/booking': return self.reply(200,self.booking_view(s))
                if self.path=='/api/shine':
                    if not self.server.shine_secret: return self.reply(200,{'enabled':False,'error':"Shine chat isn't connected to this mailbox yet."})
                    return self.reply(200,{'enabled':True,'origin':self.server.shine_origin,'token':shine_token(self.server.shine_secret,s['user']['email'],s['user'].get('name',''),shine_admin(s['user']),self.shine_photo(s['user']['email']))})
                if self.path.startswith('/api/updates/file?'):
                    return self.update_file(s,urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id',[''])[0])
                if self.path=='/api/preferences': return self.reply(200,self.server.zimbra.preferences(s['token']))
                if self.path=='/api/appearance': return self.reply(200,self.server.appearance.get(self.account(s)))
                if self.path=='/api/settings':
                    return self.reply(200,{'mailbox':self.server.zimbra.account_settings(s['token']),'ui':self.server.ui_settings.get(self.account(s)),
                        'account':self.server.zimbra.account_info(s['token']),'server':{'host':self.server.mail_host}})
                if self.path=='/api/account': return self.reply(200,self.server.zimbra.account_info(s['token']))
                if self.path=='/api/labels': return self.reply(200,self.server.zimbra.labels(s['token']))
                if self.path=='/api/filters': return self.reply(200,self.server.zimbra.filters(s['token']))
                if self.path=='/api/supervisors': return self.reply(200,self.supervisors(s))
                if self.path=='/api/joi': return self.reply(200,self.joi(s,sid))
                if self.path=='/api/avatars': return self.reply(200,{'avatars':self.avatar_versions()})
                if self.path.startswith('/api/bimi?'):
                    domain=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('domain',[''])[0].strip().lower()
                    if not DOMAIN_NAME.fullmatch(domain) or len(domain)>253: return self.send_error(404)
                    logo=self.bimi_logo(domain)
                    return self.image(logo,'image/svg+xml','private, max-age=86400') if logo else self.send_error(404)
                if self.path.startswith('/api/avatar?'):
                    email=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('email',[''])[0].strip().lower()
                    found=(self.server.avatars.get(email) or self.import_shine_photo(email)) if EMAIL.fullmatch(email) else None
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
                    perms=client.actor_perms(token,s['user']['email'],scope)
                    return self.reply(200,{**client.overview(token,scope),'permissions':PERMISSIONS,'perms':None if perms is None else sorted(perms)})
                raise APIError('Not found',404)
            except APIError as e: return self.reply(e.status,{'error':str(e)})
            except (ValueError,TypeError): return self.reply(400,{'error':'Invalid request'})
            except Exception: return self.reply(502,{'error':'Mail operation failed. Try again later.'})
        path=urllib.parse.urlsplit(self.path).path
        if path.startswith('/media/'):
            raw=self.server.media.get(path[len('/media/'):])
            if raw is None: return self.send_error(404)
            return self.image(raw,IMAGE_MIME[path.rsplit('.',1)[1]],'public, max-age=31536000, immutable')
        host=(self.headers.get('Host') or '').split(':')[0].lower()
        if host.startswith('admin-mail.'):
            # The admin site: its landing page, a sign-in page and the console itself.
            if path in ('/','/index.html'): self.path='/admin-home.html'
            elif path=='/signin': self.path='/index.html'
            elif path in ('/terms','/privacy'): self.path=path+'.html'
            elif path=='/home': self.path='/admin-home.html'
            elif path=='/admin/': return self.redirect('/admin')
            elif path=='/admin' or path in ADMIN_ASSETS or ADMIN_PAGE.fullmatch(path):
                page=path=='/admin' or bool(ADMIN_PAGE.fullmatch(path))
                try: _,s=self.session()
                except APIError: return self.redirect('/signin?next=admin') if page else self.send_error(404)
                if s['user'].get('isAdmin') is not True: return self.redirect(self.server.app_origin+'/') if page else self.send_error(404)
                if page: self.path='/admin.html'
            elif not (path.startswith(('/css/','/js/','/assets/')) or path in ('/admin-home.html','/sw.js','/manifest.webmanifest','/admin.webmanifest','/offline.html','/runtime-config.js')):
                return self.redirect(self.server.app_origin+self.path)
            return super().do_GET()
        if (path in ('/admin','/admin/') or ADMIN_PAGE.fullmatch(path)) and getattr(self.server,'admin_origin',None):
            # The console lives on the admin site; mailboxes never show it.
            return self.redirect(self.server.admin_origin+(path if ADMIN_PAGE.fullmatch(path) else '/admin'))
        if path=='/home':
            self.path='/home.html'
        if path in ('/terms','/privacy'):
            self.path=path+'.html'
        if re.fullmatch(r'/book/[a-z0-9-]{3,40}',path): self.path='/booking.html'
        if path=='/shine/sso': return self.shine_sso()
        if path=='/joi/sso': return self.joi_sso()
        if path=='/admin/':
            return self.redirect('/admin')
        if path=='/signup':
            self.path='/signup.html'
        if path=='/admin' or path in ADMIN_ASSETS or ADMIN_PAGE.fullmatch(path):
            # The console and its code are only served to signed-in administrators.
            page=path=='/admin' or bool(ADMIN_PAGE.fullmatch(path))
            try: _,s=self.session()
            except APIError: return self.redirect('/?next=admin') if page else self.send_error(404)
            if s['user'].get('isAdmin') is not True: return self.redirect('/') if page else self.send_error(404)
            if page: self.path='/admin.html'
        super().do_GET()
    def image(self, raw, mime, cache):
        self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control',cache); self.send_header('Content-Security-Policy',"default-src 'none'; sandbox")
        self.end_headers(); self.wfile.write(raw)
    def bimi_logo(self, domain):
        """A sender domain's published logo, remembered for a day (and "has none" for six hours)."""
        cache=self.server.__dict__.setdefault('bimi_cache',{}); now=time.time(); hit=cache.get(domain)
        if hit and hit[0]>now: return hit[1]
        try: link=bimi_record(domain); logo=fetch_bimi_logo(link) if link else None
        except APIError: return hit[1] if hit else None   # DNS trouble: keep what we had, try again next time
        with LOCK:
            if len(cache)>=2000: cache.clear()
            cache[domain]=(now+(86400 if logo else 21600),logo)
        return logo
    def client_ip(self):
        ip=self.client_address[0]
        try:
            if ipaddress.ip_address(ip).is_loopback and self.headers.get('X-Real-IP'): ip=str(ipaddress.ip_address(self.headers['X-Real-IP']))
        except ValueError: pass
        return ip
    def send_failed(self, s, data, error, started):
        """A web send the server refused must never vanish: record it for the admin's Undelivered page,
        keep the message in Drafts (never Sent), and tell the person exactly that."""
        z=self.server.zimbra; token=s['token']; email=s['user']['email']
        if error.status==400 and not error.code:
            # our own input check (no recipient, address typo): nothing reached the mail server; Compose stays open
            return self.reply(400,{'error':str(error)})
        if error.code=='transport':
            # no answer from Zimbra: it may have gone out anyway. Look in Sent before calling it a failure.
            try: sent=z.sent_copy(token,data,started)
            except APIError: sent=None
            if sent:
                self.log('send',email,n=1)
                return self.reply(200,{'id':sent,'accepted':True,'draftRemoved':bool(data.get('id')),'confirmedLate':True})
        recipients=','.join(a.strip() for k in ('to','cc','bcc') for a in re.split(r'[,;\n]+',str(data.get(k,''))) if a.strip())
        self.log(SEND_FAILED_KIND,email,f'{error.code or error.status}|{recipients}'[:320])
        dropped=[]
        try: draft_id=z.write_message(token,data,True).get('id')  # updates the open draft when data has its id
        except APIError:
            # Zimbra applies the same size limit to drafts: keep the text (and attachments already on the
            # server) without the new files, so the message itself is never lost.
            attachments=data.get('attachments') if isinstance(data.get('attachments'),list) else []
            dropped=[str(a.get('name') or 'attachment')[:80] for a in attachments if isinstance(a,dict) and a.get('data')]
            try: draft_id=z.write_message(token,dict(data,attachments=[a for a in attachments if isinstance(a,dict) and not a.get('data')]),True).get('id') if dropped else None
            except APIError: draft_id=None
        note=' We could not confirm it was sent, and it is not in Sent.' if error.code=='transport' else ''
        if draft_id and dropped: kept=' Your text is saved in Drafts and was not sent; attach '+', '.join(dropped)+' again (or share a link) before sending.'
        elif draft_id: kept=' Your message is saved in Drafts and was not sent.'
        else: kept=' The message was not sent. Copy your text before leaving this page.'
        self.reply(error.status if error.status>=400 else 502,{'error':str(error)+note+kept,'draftId':draft_id,'notSent':True})
    def log(self, kind, actor, target='', n=1):
        audit=getattr(self.server,'audit',None)
        if audit: audit.add(kind,actor,target,self.client_ip(),n)
        hooks=getattr(self.server,'hooks',None)
        if hooks: hooks.emit(kind,actor,target,n)  # queues only: never blocks, never raises
    def login_hosts(self):
        store=getattr(self.server,'hosts',None)
        return store.get('all') if store else {}
    def brand_for(self, domain):
        """A company's own name, line, colour and logo for the app (empty when it set none)."""
        store=getattr(self.server,'hosts',None)
        if not store or not domain: return {}
        brand=store.get('brands').get(domain)
        if not isinstance(brand,dict):  # set before brands had their own place: it lived with the sign-in address
            brand=next((e.get('brand') for e in store.get('all').values() if isinstance(e,dict) and e.get('domain')==domain and isinstance(e.get('brand'),dict)),None)
        if not isinstance(brand,dict) or not (brand.get('name') or brand.get('logo')): return {}
        logo=brand.get('logo') if MEDIA_NAME.fullmatch(str(brand.get('logo') or '')) else ''
        return {'name':brand.get('name',''),'tagline':brand.get('tagline',''),'colour':brand.get('colour',''),'logo':self.server.app_origin+'/media/'+logo if logo else '','domain':domain}
    def custom_host(self):
        """The company whose own sign-in address this request came in on, or None."""
        host=(self.headers.get('Host') or '').split(':')[0].lower()
        entry=self.login_hosts().get(host)
        return {**entry,'host':host,'brand':self.brand_for(entry.get('domain')) or {'name':'','tagline':'','colour':'','logo':'','domain':entry.get('domain')}} if isinstance(entry,dict) else None
    def login_host_action(self, session, data):
        """Admin console: see, set or remove a domain's own sign-in address and its sign-in page look."""
        client,token,scope=self.admin_session(session)
        perms=client.actor_perms(token,session['user']['email'],scope)
        if scope and perms is not None and 'roles.manage' not in perms: raise APIError('Your role does not allow this. Ask an admin for "'+PERMISSIONS['roles.manage']+'".',403)
        domain=str(data.get('domain','')).strip().lower()
        if not DOMAIN_NAME.fullmatch(domain) or (scope and domain!=scope): raise APIError('You can only change your own domain.',403)
        lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'name'},domain)); client.call(lookup,token)  # the domain exists and this admin may see it
        store=self.server.hosts; mail_host=self.server.mail_host
        with LOCK:
            hosts=store.get('all'); current=next((h for h,e in hosts.items() if e.get('domain')==domain),None)
            op=data.get('op')
            if op=='login_host_set':
                host=clean_login_host(data.get('host'),mail_host,domain)
                if hosts.get(host,{}).get('domain',domain)!=domain: raise APIError('That address is already used by another company.',409)
                if len(hosts)>=200 and host not in hosts: raise APIError('No more sign-in addresses can be added right now. Contact Dejoiy.',503)
                if not host_points_here(host,mail_host): raise APIError(f'{host} does not point to {mail_host} yet. Add a CNAME record: {host.split(".")[0]} -> {mail_host}, wait a few minutes and try again.',409)
                if current and current!=host: hosts.pop(current,None)
                hosts[host]={'domain':domain}; current=host
            elif op=='login_host_remove':
                if current: hosts.pop(current,None)
                current=None
            if op=='brand_set':
                brands=store.get('brands'); brand={**clean_brand(data),'logo':(brands.get(domain) or {}).get('logo','')}
                if data.get('removeLogo') is True: brand['logo']=''
                if data.get('logo'):
                    ext,raw=decode_image(data.get('logo'),('png','jpeg'),200*1024,'The logo')
                    brand['logo']=self.server.media.save('brand:'+domain,ext,raw)
                brands[domain]=brand; store.put('brands',brands)
            if op in ('login_host_set','login_host_remove'):
                store.put('all',hosts)
                target=getattr(self.server,'hosts_file',None)
                if target:  # the list the server's certificate job reads (deploy/custom-hosts.sh)
                    try: Path(target).write_text(''.join(h+'\n' for h in sorted(hosts)))
                    except OSError: pass
        return {'domain':domain,'host':current or '','brand':self.brand_for(domain) or {'name':'','tagline':'','colour':'','logo':''},'target':mail_host,
            'pointing':bool(current) and host_points_here(current,mail_host)}
    def domain(self, session):
        email=session['user']['email'].lower()
        return email.rsplit('@',1)[1] if '@' in email else ''
    def avatar_sig(self, email):
        key=(self.server.shine_secret or os.environ.get('SESSION_SECRET') or 'dejoiy-mail').encode()
        return hmac.new(key,('avatar:'+email.lower()).encode(),'sha256').hexdigest()[:32]
    def shine_photo(self, email):
        """The mailbox's photo as a signed link Shine (and anyone given it) can load without a Dejoiy Mail session."""
        version=self.server.avatars.version(email)
        if not version: return ''
        q=urllib.parse.urlencode({'e':email.lower(),'s':self.avatar_sig(email),'v':version})
        return f"{self.server.app_origin}/api/public/avatar?{q}"
    def public_avatar(self):
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        email=q.get('e',[''])[0].strip().lower(); sig=q.get('s',[''])[0]
        found=self.server.avatars.get(email) if EMAIL.fullmatch(email) and hmac.compare_digest(sig.encode(),self.avatar_sig(email).encode()) else None
        if not found: raise APIError('No photo',404)
        return self.image(found[1],IMAGE_MIME[found[0]],'public, max-age=31536000, immutable')
    def shine_avatar(self, data):
        """Shine sends a photo uploaded there (or '' when removed), so both apps show the same picture."""
        email=str(data.get('email','')).strip().lower()
        if not EMAIL.fullmatch(email): raise APIError('Invalid mailbox')
        if data.get('image')=='':
            self.server.avatars.delete(email); return {'ok':True,'photo':''}
        ext,raw=decode_image(data.get('image'),('png','jpeg','webp'),MAX_AVATAR_BYTES,'Profile photo')
        self.server.avatars.put(email,ext,raw)
        return {'ok':True,'photo':self.shine_photo(email)}
    def shine_photos(self):
        """{email: url} for photos people uploaded in Shine, asked for at most every 5 minutes."""
        cache=getattr(self.server,'shine_photo_cache',None)
        if cache and time.time()-cache[0]<300: return cache[1]
        try: photos=(self.shine_post('/dejoiy/photos',{}) or {}).get('photos') or {}
        except APIError: photos=cache[1] if cache else {}
        photos={str(k).lower():v for k,v in photos.items() if isinstance(v,str) and v.startswith('https://')} if isinstance(photos,dict) else {}
        self.server.shine_photo_cache=(time.time(),photos)
        return photos
    def avatar_versions(self):
        """Every mailbox photo, plus photos set only in Shine (fetched and kept here the first time they're shown)."""
        versions=self.server.avatars.versions()
        for email,url in self.shine_photos().items():
            if email not in versions: versions[email]='s'+hashlib.sha256(url.encode()).hexdigest()[:10]
        return versions
    def import_shine_photo(self, email):
        """A photo uploaded in Shine before the two apps shared photos: copy it here once."""
        url=self.shine_photos().get(email)
        if not url: return None
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'DejoiyMail'}),timeout=8) as response: raw=response.read(2*1024*1024+1)
        except (urllib.error.URLError,TimeoutError,ValueError): return None
        kind=next((k for k,ok in IMAGE_MAGIC.items() if ok(raw)),None)
        if not kind or len(raw)>2*1024*1024: return None
        self.server.avatars.put(email,IMAGE_EXT[kind],raw)
        return (IMAGE_EXT[kind],raw)
    def tell_shine_photo(self, email):
        """A photo changed here: Shine shows it too (best effort; the directory sync catches up anyway)."""
        payload={'email':email.lower(),'photo':self.shine_photo(email)}
        def send():
            try: self.shine_post('/dejoiy/photo',payload)
            except APIError: pass
        threading.Thread(target=send,daemon=True).start()
    def shine_allowed(self):
        secret=self.server.shine_secret
        auth=self.headers.get('Authorization') or ''
        if not secret or not auth.startswith('Bearer ') or not hmac.compare_digest(auth[7:].strip().encode(),secret.encode()): raise APIError('Not allowed',403)
    def shine_calendar(self, data):
        """Shine's meetings live on the same Zimbra calendar: save/delete/list events for one mailbox."""
        owner=str(data.get('owner','')).strip().lower()
        if not EMAIL.fullmatch(owner): raise APIError('Invalid mailbox')
        token=self.delegated(owner); client=self.server.zimbra; op=data.get('op')
        if op=='list':
            try: start,end=int(data.get('start')),int(data.get('end'))
            except (TypeError,ValueError): raise APIError('Invalid dates.')
            return {'events':self.cal(dcalendar.events,client,token,start,end)}
        event=data.get('event') if isinstance(data.get('event'),dict) else {}
        if op=='delete': return self.cal(dcalendar.delete_event,client,token,event)
        if op=='save': return self.cal(dcalendar.save_event,client,token,event,owner)
        raise APIError('Unknown calendar request')
    def shine_login(self, data):
        """Shine's sign-in form: check a mailbox email + password with Zimbra and say who it is.
        The password is only passed on to Zimbra, never kept. Shine's server is the caller, so the limit is per mailbox."""
        email=str(data.get('email','')).strip().lower(); password=str(data.get('password',''))
        if not EMAIL.fullmatch(email) or len(email)>320 or not password or len(password)>4096: raise APIError('Enter your Dejoiy Mail email and password.')
        with LOCK:
            now=time.time(); key='shine-login:'+email; tries=[t for t in self.server.attempts.get(key,[]) if t>now-60]
            if len(tries)>=8: raise APIError('Too many attempts; wait one minute',429)
            self.server.attempts[key]=tries+[now]
        try: token,_=self.server.zimbra.login(email,password)
        except APIError as error:
            if error.status==401: raise APIError('Wrong email or password.',401)
            raise
        user=self.server.zimbra.capabilities(token)
        try: name=self.server.zimbra.preferences(token).get('name') or ''
        except APIError: name=''
        return {'email':email,'name':name,'admin':shine_admin(user),'photo':self.shine_photo(email)}
    def shine_meeting(self, session, data):
        """'Add Shine meeting' on a calendar event: Shine makes a room for this mailbox and gives back its link."""
        if not self.server.shine_secret: raise APIError("Shine isn't connected to this mailbox yet.",503)
        guests=[g for g in re.split(r'[,;\s]+',str(data.get('guests',''))) if EMAIL.fullmatch(g)][:100]
        body=json.dumps({'host':session['user']['email'],'title':str(data.get('title') or 'Meeting')[:200],
            'start':data.get('start'),'end':data.get('end'),'guests':guests}).encode()
        request=urllib.request.Request(self.server.shine_site+'/dejoiy/meeting',data=body,method='POST',
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.server.shine_secret})
        try:
            with urllib.request.urlopen(request,timeout=15) as response: out=json.loads(response.read())
        except urllib.error.HTTPError as error:
            try: message=json.loads(error.read()).get('error')
            except (ValueError,AttributeError): message=None
            raise APIError(message or 'Shine could not make the meeting.',502)
        except (urllib.error.URLError,TimeoutError,ValueError): raise APIError('Shine is not reachable right now.',502)
        if not str(out.get('url','')).startswith('https://'): raise APIError('Shine could not make the meeting.',502)
        return {'url':out['url'],'roomCode':out.get('roomCode','')}
    def shine_post(self, path, payload):
        """Server to server call to Shine with the shared secret. None when Shine isn't connected or answers 404."""
        if not self.server.shine_secret: return None
        request=urllib.request.Request(self.server.shine_site+path,data=json.dumps(payload).encode(),method='POST',
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.server.shine_secret})
        try:
            with urllib.request.urlopen(request,timeout=8) as response: return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code==404: return None
            raise APIError('Shine is not reachable right now.',502)
        except (urllib.error.URLError,TimeoutError,ValueError): raise APIError('Shine is not reachable right now.',502)
    def shine_admin_post(self, payload):
        """Shine's admin endpoint; its own refusals ("can't switch off the super admin") come back as readable errors."""
        return shine_admin_call(self.server.shine_site,self.server.shine_secret,payload)
    def presence(self, session, data):
        """Your Active/Away dot and written status, kept in Shine so both apps show the same thing.
        A heartbeat sends idle; the status menu sends choice and/or text."""
        body={'email':session['user']['email'].lower()}
        if isinstance(data.get('idle'),bool): body['idle']=data['idle']
        if data.get('choice') in ('auto','away','busy','invisible'): body['choice']=data['choice']
        if isinstance(data.get('text'),str): body['text']=data['text'][:140]
        out=self.shine_post('/dejoiy/presence',body)
        if out is None: return {'enabled':False}
        return {'enabled':True,'choice':out.get('choice','auto'),'text':out.get('text','')}
    def people_status(self, session, data):
        """Presence and status for colleagues on your own domain (the same people who see each other's photos)."""
        domain=self.domain(session)
        emails=[e.lower() for e in (data.get('emails') or []) if isinstance(e,str) and EMAIL.fullmatch(e)]
        emails=[e for e in dict.fromkeys(emails) if e.rsplit('@',1)[1]==domain or e in JOI_MAILBOXES][:200]
        if not emails: return {'enabled':bool(self.server.shine_secret),'people':{}}
        out=self.shine_post('/dejoiy/people',{'emails':emails})
        if out is None: return {'enabled':False,'people':{}}
        return {'enabled':True,'people':out.get('people',{})}
    def joi(self, session, sid=None):
        """Where Joi's chat lives, (for DEJOIY's own people) a token so she may use internal memory,
        and the grant that lets her read this person's own mailbox while they talk to her."""
        srv=self.server; url=getattr(srv,'joi_url','https://joi-ai.dejoiy.com')
        internal=self.domain(session) in getattr(srv,'joi_internal',[])
        secret=getattr(srv,'joi_secret','')
        grant=self.joi_grant(sid,session) if sid and secret else ''
        return {'url':url,'api':getattr(srv,'joi_api',url),'token':joi_app_token(secret) if secret and internal else '',
            'grant':grant,'mailbox':srv.app_origin+'/api/joi/mailbox' if grant else ''}
    def joi_grant(self, sid, session):
        """A 12-hour grant for Joi naming this mailbox and this sign-in; signing out here ends it."""
        key=getattr(self.server,'joi_grant_key','')
        if not key: return ''
        with LOCK:
            current=SESSIONS.get(sid)
            if current is None: return ''
            if not current.get('joi_grant'):
                current['joi_grant']=secrets.token_urlsafe(18); SESSIONS[sid]=current
            gid=current['joi_grant']
        email=session['user']['email'].lower()
        return joi_signed(key,{'app':'mail','k':'grant','e':email,'g':gid,'exp':int((time.time()+min(JOI_GRANT_SECONDS,max(60,session.get('expires',0)-time.time())))*1000)})
    def supervisors(self, session):
        """Supervisors at the other companies on Dejoiy (team leads up to admins and IT) this mailbox may write to.
        Shine decides: admins switch it on or off per company or per person."""
        out=self.shine_post('/dejoiy/supervisors',{'email':session['user']['email'].lower()})
        if out is None: return {'enabled':False,'people':[]}
        people=[p for p in out.get('people',[]) if isinstance(p,dict) and EMAIL.fullmatch(str(p.get('email','')))]
        return {'enabled':True,'people':people[:500]}
    def mention_recipients(self, session, data):
        """Group mentions in a mail, like in Shine chat:
        @all  in To/Cc/Bcc = every mailbox on your own domain;
        @allS              = every mailbox on Dejoiy Mail, every domain (DEJOIY super admins and IT only);
        @Joi  in the text  = Joi is copied in (Cc) and answers everyone on the mail.
        The group goes in Bcc, so nobody sees the whole list; the mail is To you when there's no one else."""
        data=dict(data); me=session['user']['email'].lower(); fields={}; groups=set()
        for kind in ('to','cc','bcc'):
            keep=[]
            for address in re.split(r'[,;\n]+',str(data.get(kind,''))):
                address=address.strip()
                if address.lower() in ('@all','@alls'): groups.add('allS' if address.lower()=='@alls' else 'all')
                elif address: keep.append(address)
            fields[kind]=keep
        if groups:
            user=session['user']; mine=self.domain(session)
            if 'allS' in groups and not (user.get('canManageRoles') is True or (user.get('isAdmin') is True and mine in getattr(self.server,'joi_internal',[]))):
                raise APIError('Only DEJOIY super admins and IT can mail everyone with @allS. Use @all for your own domain.',403)
            every=[p['email'] for p in self.mailboxes() if p['active'] and p['email']!=me and p['email'] not in JOI_MAILBOXES]
            group=every if 'allS' in groups else [e for e in every if e.rsplit('@',1)[1]==mine]
            have={a.lower() for k in fields for a in fields[k]}
            fields['bcc']+=[e for e in group if e not in have]
            if not fields['to']: fields['to']=[me]
        joi=sorted(JOI_MAILBOXES)[0]
        if re.search(r'(^|[\s>(])@joi\b',plain(str(data.get('body',''))),re.I) and joi not in {a.lower() for k in fields for a in fields[k]} and me!=joi:
            fields['cc'].append(joi)
        for kind in fields: data[kind]=', '.join(fields[kind])
        return data
    def mailboxes(self):
        """Every real mailbox (system and spam-training boxes left out)."""
        provisioner=getattr(self.server,'provisioner',None)
        if not provisioner: raise APIError('This needs the service admin account (PROVISION_ADMIN).',503)
        out=provisioner.admin.call(node(ADMIN,'GetAllAccountsRequest'),provisioner.token())
        people=[]
        for account in out.findall('{'+ADMIN+'}account'):
            a={x.get('n'):x.text or '' for x in account.findall('{'+ADMIN+'}a')}
            email=(account.get('name') or '').lower()
            if a.get('zimbraIsSystemResource')=='TRUE' or not EMAIL.fullmatch(email) or email.startswith(('galsync','spam.','ham.','virus-quarantine.')): continue
            people.append({'email':email,'a':a,'active':a.get('zimbraAccountStatus','active')=='active'})
        return people
    def shine_directory(self):
        """Every mailbox, for Shine's people list. Server to server only: Shine sends the shared secret."""
        self.shine_allowed()
        provisioner=getattr(self.server,'provisioner',None)
        if not provisioner: raise APIError('The directory needs the service admin account (PROVISION_ADMIN).',503)
        people=[]
        for box in self.mailboxes():
            a=box['a']; email=box['email']
            admin='platform' if a.get('zimbraIsAdminAccount')=='TRUE' else 'company' if a.get('zimbraIsDelegatedAdminAccount')=='TRUE' else ''
            people.append({'email':email,'name':a.get('displayName') or '','active':a.get('zimbraAccountStatus','active')=='active',
                'admin':admin,'department':a.get('ou',''),'title':a.get('title',''),'photo':self.shine_photo(email)})
        return {'people':people}
    def shine_sso(self):
        # Shine's "Continue with Dejoiy Mail": signed in here -> back to Shine with a token; otherwise sign in first.
        back=safe_return(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('return',[''])[0])
        if not self.server.shine_secret: return self.send_error(503,'Shine is not connected')
        try: _,s=self.session()
        except APIError: return self.redirect('/?next=shine&return='+urllib.parse.quote(back,safe=''))
        t=shine_token(self.server.shine_secret,s['user']['email'],s['user'].get('name',''),shine_admin(s['user']),self.shine_photo(s['user']['email']))
        return self.redirect(self.server.shine_origin+'/auth/dejoiy#t='+urllib.parse.quote(t,safe='')+'&next='+urllib.parse.quote(back,safe=''))
    def joi_sso(self):
        # Joi's "Sign in with Dejoiy Mail": signed in here -> back to Joi with a 5-minute token proving this mailbox.
        srv=self.server
        if not getattr(srv,'joi_secret',''): return self.send_error(503,'Joi is not connected')
        try: sid,s=self.session()
        except APIError: return self.redirect('/?next=joi')
        # 'g' is the mailbox grant (see joi_grant): Joi keeps it and sends it with POST /api/joi/mailbox
        t=joi_signed(srv.joi_secret,{'app':'mail','k':'login','e':s['user']['email'].lower(),'n':s['user'].get('name',''),'exp':int((time.time()+300)*1000),'d':secrets.token_urlsafe(9),'g':self.joi_grant(sid,s)})
        return self.redirect(srv.joi_url+'/?dmail='+urllib.parse.quote(t,safe=''))
    def joi_mailbox(self, data):
        """Joi's server reading one mailbox for its owner, who signed in to Joi with Dejoiy Mail.
        Joi signs each request (1 minute) with the mail-app secret AND sends the grant this server gave
        that person (signed with a key Joi does not have), so she can only read the mailbox of someone
        who opened her from here and is still signed in. Read-only: the newest mail as text fields."""
        c=joi_read(getattr(self.server,'joi_secret',''),data.get('token'),'mailbox',120)
        if not c or not EMAIL.fullmatch(str(c.get('e',''))): raise APIError('Not allowed',403)
        g=joi_read(getattr(self.server,'joi_grant_key',''),data.get('grant'),'grant',JOI_GRANT_SECONDS+60)
        if not joi_grant_ok(c,g,SESSIONS): raise APIError('Ask the person to open Joi from Dejoiy Mail again.',403)
        result=self.server.zimbra.messages(self.delegated(c['e'].lower()))
        def short(m,size): return {'date':m.get('date'),'from':m.get('from'),'to':m.get('to'),'subject':m.get('subject'),'read':m.get('read'),
            'hasAttachment':m.get('hasAttachment'),'text':plain(str(m.get('body','')))[:size]}
        mails=result.get('emails',[])
        inbox=[m for m in mails if m.get('folder')=='inbox']; sent=[m for m in mails if m.get('folder')=='sent']
        return {'inbox':[short(m,1500 if i<3 else 200) for i,m in enumerate(inbox[:20])],'unread':sum(1 for m in inbox if not m.get('read')),'sent':[short(m,200) for m in sent[:5]]}
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
            return self.reply(200,{'token':token,'domain':domain,'email':pending['email'],'record':{'type':'TXT','host':'@','value':pending['code']},
                'records':signup_records(pending,self.server.mail_host,getattr(self.server.admin,'dkim_dir',None))})
        token=str(data.get('token',''))
        pending=self.server.signups.get(token) if 20<=len(token)<=64 else None
        if not pending: raise APIError('This sign-up has expired. Start again.',404)
        if op not in ('check','complete'): raise APIError('Not found',404)
        verified=pending['code'] in txt_records(pending['domain'])
        if op=='check':
            records=signup_records(pending,self.server.mail_host,getattr(self.server.admin,'dkim_dir',None)); records[0]['ok']=verified; records[0]['status']='ok' if verified else 'missing'
            return self.reply(200,{'verified':verified,'domain':pending['domain'],'email':pending['email'],'company':pending['company'],'record':{'type':'TXT','host':'@','value':pending['code']},'records':records})
        password=data.get('password')
        problem=password_problem(password,pending['email'])
        if problem: raise APIError(problem)
        if not verified: raise APIError('We could not find the TXT record yet. DNS changes can take a few minutes.',409)
        if provisioner.domain_exists(pending['domain']): raise APIError('This domain already uses Dejoiy Mail.',409)
        provisioner.provision(pending['domain'],pending['company'],pending['email'],pending['name'],password)
        self.server.signups.delete(token)
        return self.start_session(pending['email'],password)
    # ---------- update boxes: Dejoiy Updates for every mailbox, and each company's own box ----------
    def org(self, session):
        """The company box name and whether this person may post there, read with the service admin
        (people without admin rights cannot read their own role). Cached on the session for 5 minutes."""
        cached=session.get('org')
        if cached and cached.get('at',0)>time.time()-300: return cached
        user=session['user']; domain=self.domain(session); info={'at':time.time(),'box':'','post':bool(user.get('isAdmin'))}
        provisioner=getattr(self.server,'provisioner',None)
        if provisioner and domain:
            try:
                token=provisioner.token(); admin=provisioner.admin
                found=node(ADMIN,'GetDomainRequest'); found.append(node(ADMIN,'domain',{'by':'name'},domain))
                notes=attr(admin.call(found,token).find('{'+ADMIN+'}domain'),'zimbraNotes')
                me=node(ADMIN,'GetAccountRequest'); me.append(node(ADMIN,'account',{'by':'name'},user['email']))
                title=attr(admin.call(me,token).find('{'+ADMIN+'}account'),'title')
                info.update(box=read_org(notes)['boxName'],post='updates.post' in role_perms(read_roles(notes),title,bool(user.get('isAdmin'))))
            except (APIError,AttributeError): pass
        session['org']=info; return info
    def updates_view(self, session):
        org=self.org(session); domain=self.domain(session); store=self.server.updates
        saved=store.get('dejoiy'); team=session['user'].get('canManageRoles') is True
        dejoiy=dejoiy_posts(saved)
        # Home-page-only posts stay out of mailboxes; the Dejoiy team still sees them, to manage them.
        if not team: dejoiy=[p for p in dejoiy if p.get('audience','both')!='external']
        return {'dejoiy':dejoiy,'company':{'name':org['box'] or 'Company updates','domain':domain,
            'posts':store.get('company:'+domain).get('posts',[])},'can':{'dejoiy':session['user'].get('canManageRoles') is True,'company':org['post']}}
    def post_update(self, session, data):
        box=data.get('box'); domain=self.domain(session)
        if box=='dejoiy': allowed=session['user'].get('canManageRoles') is True; key='dejoiy'
        elif box=='company': allowed=self.org(session)['post']; key='company:'+domain
        else: raise APIError('Choose where to post.')
        if not allowed: raise APIError('Your role cannot post here. Ask your admin for "Post in the company box".' if box=='company' else 'Only the Dejoiy team posts Dejoiy Updates.',403)
        with UPDATES_LOCK:
            saved=self.server.updates.get(key)
            posts=dejoiy_posts(saved) if key=='dejoiy' else saved.get('posts',[])
            if data.get('op')=='delete':
                for p in posts:
                    if p.get('id')==data.get('id'):
                        for f in p.get('files') or []: self.server.update_files.put('file:'+f['id'],{})
                posts=[p for p in posts if p.get('id')!=data.get('id')]
            elif data.get('op')=='pin':
                # One pinned post per box: pinning another moves the pin; pinning the pinned one unpins it.
                posts=[{**p,'pinned':p.get('id')==data.get('id') and not p.get('pinned')} for p in posts]
            elif data.get('op')=='post':
                title=str(data.get('title','')).strip(); body=str(data.get('body','')).strip()
                if not 1<=len(title)<=120 or any(ord(c)<32 for c in title): raise APIError('Give the update a title of up to 120 characters.')
                if not 1<=len(body)<=4000: raise APIError('Write the update in up to 4000 characters.')
                kind=data.get('kind') if data.get('kind') in UPDATE_KINDS else 'news'
                link=None
                if data.get('link'):
                    url=str(data['link'].get('url','')).strip() if isinstance(data['link'],dict) else ''
                    if not (re.fullmatch(r'https://[^\s<>"]{3,500}',url) or re.fullmatch(r'/[A-Za-z0-9/#?=&._-]{0,200}',url)): raise APIError('Links must start with https://')
                    link={'url':url,'label':str(data['link'].get('label','')).strip()[:40] or 'Open link'}
                post={'id':secrets.token_hex(8),'kind':kind,'title':title,'body':body,'author':session['user'].get('name') or session['user']['email'],
                    'email':session['user']['email'],'date':int(time.time()*1000),'pinned':False,'link':link,'files':[],
                    # Dejoiy Updates can go to mailboxes (internal), the home pages (external) or both; company posts stay inside.
                    'audience':(data.get('audience') if data.get('audience') in ('internal','external','both') else 'both') if box=='dejoiy' else 'internal'}
                post['files']=self.store_update_files(data.get('files'),key,post['id'])
                posts=[post,*posts][:100]
            else: raise APIError('Unsupported update operation.')
            self.server.updates.put(key,{'posts':posts,'seen':SEED_UPDATE_IDS} if key=='dejoiy' else {'posts':posts})
        return self.updates_view(session)
    # ---------- calendar and booking links ----------
    def cal(self, fn, *args):
        try: return fn(*args)
        except dcalendar.CalendarError as e: raise APIError(str(e),e.code)
    def delegated(self, email):
        """A short-lived mailbox token for the booking owner, issued by the service admin: public
        visitors never hold a token, and the owner doesn't need to be signed in."""
        provisioner=getattr(self.server,'provisioner',None)
        if not provisioner: raise APIError('Booking links are not set up on this server yet.',503)
        return delegated_token(provisioner,email)
    def booking_view(self, session):
        email=session['user']['email']; store=self.server.booking; saved=store.get('user:'+email)
        if not saved.get('slug'):
            slug=dcalendar.make_slug(email,lambda x:bool(store.get('slug:'+x)))
            saved={**dcalendar.DEFAULT_BOOKING,'slug':slug,'name':session['user'].get('name') or email}
            store.put('user:'+email,saved); store.put('slug:'+slug,{'email':email})
        return {**{k:saved.get(k,v) for k,v in dcalendar.DEFAULT_BOOKING.items()},'slug':saved['slug'],'url':self.server.app_origin+'/book/'+saved['slug'],
            'ready':bool(getattr(self.server,'provisioner',None))}
    def save_booking(self, session, data):
        email=session['user']['email']; store=self.server.booking; current=store.get('user:'+email) or self.booking_view(session) and store.get('user:'+email)
        settings=self.cal(dcalendar.clean_booking,data,current)
        slug=str(data.get('slug',current['slug'])).strip().lower()
        if slug!=current['slug']:
            if not dcalendar.SLUG.fullmatch(slug): raise APIError('Use 3 to 40 lowercase letters, numbers and dashes for your link.')
            if store.get('slug:'+slug).get('email') not in (None,email): raise APIError('That link is taken. Try another.')
            store.put('slug:'+current['slug'],{}); store.put('slug:'+slug,{'email':email})
        store.put('user:'+email,{**settings,'slug':slug,'name':session['user'].get('name') or email})
        return self.booking_view(session)
    def booking_owner(self, slug):
        email=self.server.booking.get('slug:'+slug).get('email') if dcalendar.SLUG.fullmatch(slug or '') else None
        settings=self.server.booking.get('user:'+email) if email else {}
        if not settings.get('enabled'): raise APIError('This booking link is not available.',404)
        return email,settings
    def free_slots(self, email, settings):
        now=int(time.time()*1000); end=now+(settings['window']+2)*dcalendar.DAY_MS
        busy=self.cal(dcalendar.busy,self.server.zimbra,self.delegated(email),email,now,end)
        return self.cal(dcalendar.slots,settings,busy,now)
    def public_booking(self, slug):
        email,settings=self.booking_owner(slug)
        return {'name':settings.get('name',''),'title':settings['title'],'duration':settings['duration'],'tz':settings['tz'],
            'description':settings.get('description',''),'location':settings.get('location',''),'slots':self.free_slots(email,settings)}
    def make_booking(self, slug, data):
        email,settings=self.booking_owner(slug)
        with BOOKING_LOCK:  # two visitors can't take the same time
            free=self.free_slots(email,settings)
            return self.cal(dcalendar.book,self.server.zimbra,self.delegated(email),email,settings,data,free)
    def store_update_files(self, files, box, post):
        """Files attached to an update: up to 6, 10 MB together, kept with the post's box so only
        people who can see that box can open them."""
        if not files: return []
        if not isinstance(files,list) or len(files)>6: raise APIError('Attach up to 6 files.')
        decoded=[]; total=0
        for item in files:
            if not isinstance(item,dict): raise APIError('Invalid file.')
            try: raw=base64.b64decode(str(item.get('data','')),validate=True)
            except (ValueError,binascii.Error): raise APIError('Invalid file data.')
            total+=len(raw)
            if not raw or total>MAX_UPDATE_FILES: raise APIError('Files must total 10 MB or less.')
            name=str(item.get('name','file')).strip()[:120] or 'file'
            if any(ord(c)<32 or c in '/\\' for c in name): raise APIError('Invalid file name.')
            decoded.append((raw,name))
        saved=[]
        for raw,name in decoded:
            image=next((k for k,test in IMAGE_MAGIC.items() if test(raw)),None)  # images by their bytes, never by name
            ident=secrets.token_hex(12)
            self.server.update_files.put('file:'+ident,{'box':box,'post':post,'name':name,'image':image,'data':base64.b64encode(raw).decode()})
            saved.append({'id':ident,'name':name,'size':len(raw),'image':bool(image)})
        return saved
    def update_photo(self, name):
        """A default post's photo, fetched from Unsplash once and then served from here, so visitors'
        browsers never call a third party."""
        source=UPDATE_PHOTOS.get(name)
        if not source: raise APIError('Photo not found.',404)
        cached=self.server.update_files.get('photo:'+name)
        if cached: raw=base64.b64decode(cached['data'])
        else:
            url=f'https://images.unsplash.com/{source}?w=960&h=600&fit=crop&crop=faces&q=72&fm=jpg'
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'DejoiyMail/1.0'}),timeout=15) as r: raw=r.read(4*1024*1024+1)
            except (OSError,ValueError): raise APIError('Photo unavailable.',502)
            if len(raw)>4*1024*1024 or not IMAGE_MAGIC['jpeg'](raw): raise APIError('Photo unavailable.',502)
            self.server.update_files.put('photo:'+name,{'data':base64.b64encode(raw).decode()})
        return self.image(raw,'image/jpeg','public, max-age=604800')
    def update_file(self, session, ident):
        found=self.server.update_files.get('file:'+ident) if re.fullmatch(r'[0-9a-f]{24}',ident or '') else {}
        allowed=('dejoiy',) if session is None else ('dejoiy','company:'+self.domain(session))
        if not found or found.get('box') not in allowed: raise APIError('File not found.',404)
        raw=base64.b64decode(found['data'])
        if found.get('image'): return self.image(raw,IMAGE_MIME['jpg' if found['image']=='jpeg' else found['image']],'private, max-age=86400')
        self.send_response(200); self.send_header('Content-Type','application/octet-stream')
        self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(found['name'],safe=''))
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','private, no-store')
        self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def webhook_action(self, s, data):
        """A company's webhooks (see webhooks.py). Same permission as the company's domain settings."""
        hooks=getattr(self.server,'hooks',None)
        if not hooks: raise APIError('Webhooks are not switched on for this server.',503)
        client,token,scope=self.admin_session(s)
        perms=client.actor_perms(token,s['user']['email'],scope)
        if scope and perms is not None and 'roles.manage' not in perms:
            raise APIError('Your role does not allow this. Ask an admin for "'+PERMISSIONS['roles.manage']+'".',403)
        domain=webhook_domain(scope,data.get('domain'))
        if not scope:  # a platform admin picks the company; it must be a real one
            lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'name'},domain))
            if client.call(lookup,token).find('{'+ADMIN+'}domain') is None: raise APIError('Domain not found.',404)
        payload={k:data.get(k) for k in ('id','url','events','active')}
        try: out=hooks.action(data['op'],payload,domain)
        except WebhookError as e: raise APIError(str(e))
        if data['op']!='webhooks_get': self.log('admin:'+data['op'],s['user']['email'],domain+' '+str(payload.get('url') or payload.get('id') or '')[:200])
        return out
    def apitoken_action(self, s, data):
        """A company's API tokens (see apitokens.py). Same permission as webhooks: the company's domain settings."""
        tokens=getattr(self.server,'api_tokens',None)
        if not tokens: raise APIError('API tokens are not switched on for this server.',503)
        client,token,scope=self.admin_session(s)
        perms=client.actor_perms(token,s['user']['email'],scope)
        if scope and perms is not None and 'roles.manage' not in perms:
            raise APIError('Your role does not allow this. Ask an admin for "'+PERMISSIONS['roles.manage']+'".',403)
        domain=webhook_domain(scope,data.get('domain'))
        if not scope:
            lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'name'},domain))
            if client.call(lookup,token).find('{'+ADMIN+'}domain') is None: raise APIError('Domain not found.',404)
        payload={k:data.get(k) for k in ('id','name','scopes','days')}
        try: out=tokens.action(data['op'],payload,domain,s['user']['email'])
        except TokenError as e: raise APIError(str(e))
        if data['op']!='apitokens_get':   # never the token itself: its name and id only
            self.log('admin:'+data['op'],s['user']['email'],domain+' '+str(payload.get('name') or out.get('revoked') or '')[:60]+' '+str(out.get('id') or payload.get('id') or ''))
        return out
    def automation_action(self, s, data):
        """A company's ready-made automations (see automations.py). Same permission as webhooks."""
        autos=getattr(self.server,'automations',None)
        if not autos: raise APIError('Automations are not switched on for this server.',503)
        client,token,scope=self.admin_session(s)
        perms=client.actor_perms(token,s['user']['email'],scope)
        if scope and perms is not None and 'roles.manage' not in perms:
            raise APIError('Your role does not allow this. Ask an admin for "'+PERMISSIONS['roles.manage']+'".',403)
        domain=webhook_domain(scope,data.get('domain'))
        if not scope:
            lookup=node(ADMIN,'GetDomainRequest'); lookup.append(node(ADMIN,'domain',{'by':'name'},domain))
            if client.call(lookup,token).find('{'+ADMIN+'}domain') is None: raise APIError('Domain not found.',404)
        try: out=autos.action(data['op'],{'kind':data.get('kind'),'settings':data.get('settings')},domain,s['user']['email'])
        except AutomationError as e: raise APIError(str(e))
        if data['op']!='automations_get':
            on=(out.get(str(data.get('kind'))) or {}).get('on')
            self.log('admin:automation_save',s['user']['email'],domain+' '+str(data.get('kind'))[:40]+(' on' if on else ' off'))
        return out
    def api_v1(self, method):
        """The automation API: Authorization: Bearer <API token>, only ever the token's own company domain.
        Any missing, wrong, expired or revoked token gets the same bare 401."""
        try:
            path,_,query=self.path.partition('?')
            tokens=getattr(self.server,'api_tokens',None)
            auth=self.headers.get('Authorization','')
            tok=tokens.check(auth[7:]) if tokens and auth[:7].lower()=='bearer ' else None
            if not tok: return self.reply(401,{'error':'Unauthorized'})
            need=API_ROUTES.get((method,path))
            if not need: raise APIError('Not found',404)
            if need not in tok['scopes']: raise APIError('This token is not allowed to do that.',403)
            if not tokens.allow(tok['id'],need): raise APIError('Too many requests for this token; wait a minute.',429)
            if method=='GET': data={k:v[-1] for k,v in urllib.parse.parse_qs(query).items()}
            else:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise APIError('JSON required',415)
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_API_BYTES: raise APIError('Request too large or empty',413)
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise APIError('JSON object required')
        except APIError as e: return self.reply(e.status,{'error':str(e)})
        except (ValueError,TypeError): return self.reply(400,{'error':'Invalid request'})
        who=tok['by']; note='token '+tok['id']
        try:
            if need=='shine.post': out=self.api_shine_post(tok,data)
            else:
                who=self.api_mailbox(tok,data)
                mail_token=self.api_delegated(who)
                if need=='mail.send': out=self.api_send(tok,who,mail_token,data); note+=' to '+str(out.pop('_count'))
                elif need=='mail.label': out=self.api_label(who,mail_token,data)
                else: out=self.api_messages(tok,who,mail_token,data)
        except APIError as e:
            self.log('api:'+need,who,note+' failed '+str(e.status)); return self.reply(e.status,{'error':str(e)})
        except (ValueError,TypeError):
            self.log('api:'+need,who,note+' failed 400'); return self.reply(400,{'error':'Invalid request'})
        except Exception:
            self.log('api:'+need,who,note+' failed 502'); return self.reply(502,{'error':'Mail operation failed. Try again later.'})
        if need=='mail.send':
            n=int(note.rsplit(' ',1)[1]); self.log('send',who,note,n=n)   # counts in Reports and fires 'mail.sent' webhooks, like the app
        else: self.log('api:'+need,who,note)
        return self.reply(200,out)
    def api_mailbox(self, tok, data):
        email=str(data.get('mailbox') or '').strip().lower()
        if not EMAIL.fullmatch(email) or len(email)>320: raise APIError('Give "mailbox": an address of your company.')
        if email.rsplit('@',1)[1]!=tok['domain']: raise APIError('This token only reaches mailboxes of '+tok['domain']+'.',403)
        return email
    def api_delegated(self, email):
        try: return self.delegated(email)
        except APIError as e:
            if e.code=='account.NO_SUCH_ACCOUNT': raise APIError('Mailbox not found.',404)
            raise
    def api_send(self, tok, mailbox, token, data):
        to=data.get('to'); to=to if isinstance(to,list) else re.split(r'[,;\s]+',str(to or ''))
        to=[str(a).strip() for a in to if str(a).strip()]
        if not to or len(to)>20 or any(not EMAIL.fullmatch(a) or len(a)>320 for a in to): raise APIError('Give "to": 1 to 20 email addresses.')
        subject=str(data.get('subject') or '')
        if len(subject)>500 or any(ord(c)<32 for c in subject): raise APIError('"subject" must be one line of up to 500 characters.')
        text,markup=data.get('text'),data.get('html')
        if markup is not None:
            if not isinstance(markup,str) or len(markup)>500000: raise APIError('"html" must be text of up to 500 KB.')
            body=markup
        elif isinstance(text,str) and len(text)<=500000: body=html.escape(text).replace('\n','<br>')
        else: raise APIError('Give "text" or "html".')
        if not subject and not body.strip(): raise APIError('Give a subject or a body.')
        out=self.server.zimbra.write_message(token,{'to':','.join(to),'subject':subject,'body':body},sender=mailbox)
        return {'ok':True,'id':out.get('id'),'_count':len(to)}
    def api_label(self, mailbox, token, data):
        mid=str(data.get('id') or '')
        if not re.fullmatch(r'\d{1,12}',mid): raise APIError('Give "id": the message id.')
        label=str(data.get('label') or '').strip()
        if not label: raise APIError('Give "label".')
        self.server.zimbra.action(token,{'ids':[mid],'op':'label','label':label})
        return {'ok':True}
    def api_messages(self, tok, mailbox, token, data):
        folder=str(data.get('folder') or 'inbox')
        if folder not in ('inbox','sent'): raise APIError('"folder" is inbox or sent.')
        try: limit=int(data.get('limit') or 20)
        except ValueError: raise APIError('"limit" is a number from 1 to 50.')
        if not 1<=limit<=50: raise APIError('"limit" is a number from 1 to 50.')
        body=str(data.get('body') or '') in ('1','true')
        if body and 'mail.read.body' not in tok['scopes']: raise APIError('This token is not allowed to read the text of mail.',403)
        if body: limit=min(limit,20)
        r=node(MAIL,'SearchRequest',{'types':'message','limit':str(limit),'sortBy':'dateDesc','recip':'2'}); r.append(node(MAIL,'query',text='in:'+folder))   # recip=2: senders and recipients
        out=[]
        for m in self.server.zimbra.call(r,token).findall('{'+MAIL+'}m'):
            addresses=m.findall('{'+MAIL+'}e'); subject=m.find('{'+MAIL+'}su'); flags=m.get('f','')
            item={'id':m.get('id'),'date':int(m.get('d') or 0),'from':next((e.get('a','') for e in addresses if e.get('t')=='f'),''),
                'to':[e.get('a','') for e in addresses if e.get('t')=='t'],'subject':subject.text or '' if subject is not None else '',
                'read':'u' not in flags,'labels':[x for x in (m.get('tn') or '').split(',') if x]}
            if body:
                req=node(MAIL,'GetMsgRequest'); req.append(node(MAIL,'m',{'id':m.get('id'),'read':'0','html':'0'}))
                full=self.server.zimbra.call(req,token).find('{'+MAIL+'}m'); texts=[]
                for part in (full.iter('{'+MAIL+'}mp') if full is not None else []):
                    content=part.find('{'+MAIL+'}content')
                    if content is not None and part.get('ct') in ('text/plain','text/html') and not part.get('filename'): texts.append((part.get('ct'),content.text or ''))
                item['text']=(next((v for t,v in texts if t=='text/plain'),None) or plain(next((v for t,v in texts if t=='text/html'),'')))[:20000]
            out.append(item)
        return {'mailbox':mailbox,'folder':folder,'messages':out}
    def api_shine_post(self, tok, data):
        channel=str(data.get('channel') or '').strip().lstrip('#')
        text=str(data.get('text') or '').strip()
        if not channel or len(channel)>100: raise APIError('Give "channel": the Shine channel name.')
        if not text or len(text)>4000: raise APIError('Give "text" of up to 4000 characters.')
        out=self.shine_admin_post({'op':'post','scope':tok['domain'],'actor':tok['by'],'channel':channel,'text':text})
        return {'ok':True,'channel':out.get('channel',channel)}
    def admin_session(self, session):
        client=getattr(self.server,'admin',None)
        if not client: raise APIError('Mail administration is not configured on this server.',503)
        if not session.get('admin_token') or session.get('admin_expires',0)<=time.time():
            raise APIError('Sign in to Dejoiy Mail Admin to continue.',403)
        return client,session['admin_token'],session.get('admin_scope')
    def do_POST(self):
        if self.path.split('?',1)[0].startswith('/api/v1/'): return self.api_v1('POST')
        try:
            # Shine's server asking for calendar work: no browser, so no Origin; the shared secret instead.
            if self.path=='/api/joi/mailbox':
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_REQUEST_BYTES: raise APIError('Request too large or empty',413)
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise APIError('JSON object required')
                return self.reply(200,self.joi_mailbox(data))
            if self.path in ('/api/shine/calendar','/api/shine/login','/api/shine/avatar'):
                self.shine_allowed()
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_REQUEST_BYTES: raise APIError('Request too large or empty',413)
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise APIError('JSON object required')
                if self.path=='/api/shine/avatar': return self.reply(200,self.shine_avatar(data))
                return self.reply(200,self.shine_calendar(data) if self.path=='/api/shine/calendar' else self.shine_login(data))
            origin=self.headers.get('Origin')
            custom=self.custom_host()  # a company's own verified sign-in address counts as this site, for itself only
            if not origin or origin not in (self.server.app_origin,getattr(self.server,'admin_origin',None),'https://'+custom['host'] if custom else None): raise APIError('Invalid request origin',403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise APIError('JSON required',415)
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_REQUEST_BYTES: raise APIError('Request too large or empty',413)
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise APIError('JSON object required')
            if not self.server.zimbra: raise APIError('Mail server setup is pending. Contact your administrator.',503)
            booking=self.path.startswith('/api/public/booking/')
            if self.path in ('/api/login','/api/admin/login') or self.path.startswith('/api/signup/') or booking:
                with LOCK:
                    now=time.time(); attempts=self.server.attempts
                    for key in list(attempts):
                        attempts[key]=[t for t in attempts[key] if t>now-60]
                        if not attempts[key]: del attempts[key]
                    key=self.client_address[0]
                    if ipaddress.ip_address(key).is_loopback and self.headers.get('X-Real-IP'):
                        key=str(ipaddress.ip_address(self.headers['X-Real-IP']))
                    # Sign-up polls DNS, so it gets its own, larger allowance than password attempts.
                    signup=self.path.startswith('/api/signup/'); key+='#signup' if signup else '#book' if booking else ''
                    if len(attempts.get(key,[]))>=(30 if signup else 5 if booking else 10): raise APIError('Too many attempts; wait one minute',429)
                    attempts.setdefault(key,[]).append(now)
            if self.path.startswith('/api/signup/'): return self.signup(self.path[len('/api/signup/'):],data)
            if booking: return self.reply(200,self.make_booking(self.path.rsplit('/',1)[1],data))
            if self.path=='/api/login':
                email=str(data.get('email','')).strip(); password=str(data.get('password',''))
                if not email or len(email)>320 or not password or len(password)>4096: raise APIError('Enter an email and password')
                if custom:  # on a company's own address only that company signs in; "priya" means priya@theirdomain
                    if '@' not in email: email=email+'@'+custom['domain']
                    if not email.lower().endswith('@'+custom['domain']): raise APIError('This sign-in page is for '+custom['domain']+' mailboxes. Others sign in at '+self.server.app_origin.split('//')[1]+'.',403)
                try: out=self.start_session(email,password)
                except APIError:
                    if EMAIL.fullmatch(email): self.log('signin_failed',email)
                    raise
                self.log('signin',email)
                return out
            sid,s=self.session()
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): raise APIError('Invalid request token',403)
            if self.path=='/api/dns':
                domain=self.domain(s)
                return self.reply(200,{'domain':domain,'records':domain_records(domain,self.server.mail_host,getattr(self.server.admin,'dkim_dir',None))})
            if self.path=='/api/logout':
                with LOCK: SESSIONS.pop(sid,None)
                return self.reply(200,{'ok':True},'dejoiy_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
            if self.path=='/api/admin/login':
                client=getattr(self.server,'admin',None)
                if not client: raise APIError('Mail administration is not configured on this server.',503)
                password=str(data.get('password',''))
                if not password or len(password)>4096: raise APIError('Enter your administrator password.')
                try: token,lifetime=client.login(s['user']['email'],password)
                except APIError:
                    self.log('admin_signin_failed',s['user']['email']); raise
                self.log('admin_signin',s['user']['email'])
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
            if self.path=='/api/admin/action' and data.get('op') in ('shine_summary','shine_set_active','shine_end_meeting'):
                # Shine (chat and meetings) managed from this console: Shine does the work, limited to this admin's company
                client,token,scope=self.admin_session(s)
                perms=client.actor_perms(token,s['user']['email'],scope)
                if data['op']!='shine_summary' and scope and perms is not None and 'mailboxes.manage' not in perms:
                    raise APIError('Your role does not allow this. Ask an admin for "'+PERMISSIONS['mailboxes.manage']+'".',403)
                payload={'op':data['op'][6:],'actor':s['user']['email'].lower(),**({'scope':scope} if scope else {})}
                if data['op']=='shine_set_active':
                    email=str(data.get('email','')).strip().lower()
                    if not EMAIL.fullmatch(email) or (scope and not email.endswith('@'+scope)): raise APIError('You can only manage people in your own company.',403)
                    payload.update(email=email,active=data.get('active') is True)
                if data['op']=='shine_end_meeting': payload['meetingId']=str(data.get('meetingId',''))[:64]
                out=self.shine_admin_post(payload)
                if data['op']!='shine_summary': self.log('admin:'+data['op'],s['user']['email'],payload.get('email') or payload.get('meetingId'))
                return self.reply(200,out)
            if self.path=='/api/admin/action' and zconsole.is_console_op(data.get('op')):
                # the full mail-server console (Monitor, Manage, Configure, Tools, Search): see zconsole.py
                client,token,scope=self.admin_session(s)
                perms=client.actor_perms(token,s['user']['email'],scope)
                def global_admin():
                    lookup=node(ADMIN,'GetAccountRequest'); lookup.append(node(ADMIN,'account',{'by':'name'},s['user']['email']))
                    account=client.call(lookup,token).find('{'+ADMIN+'}account')
                    if account is None or attr(account,'zimbraIsAdminAccount')!='TRUE': raise APIError('Only a full administrator can change this.',403)
                console=zconsole.Console(client,token,s['user']['email'],scope,perms,APIError,global_admin)
                console.undelivered=getattr(self.server,'undelivered',None)
                console.failed_sends=self.server.audit.failures if getattr(self.server,'audit',None) else None
                out=console.run(data)
                if data['op'] not in zconsole.LOOKUPS:
                    self.log('admin:'+data['op'],s['user']['email'],str(data.get('email') or data.get('id') or data.get('domain') or data.get('name') or data.get('grantee') or data.get('queue') or '')[:200])
                return self.reply(200,out)
            if self.path=='/api/admin/action' and data.get('op') in WEBHOOK_OPS:
                return self.reply(200,self.webhook_action(s,data))
            if self.path=='/api/admin/action' and data.get('op') in AUTOMATION_OPS:
                return self.reply(200,self.automation_action(s,data))
            if self.path=='/api/admin/action' and data.get('op') in APITOKEN_OPS:
                return self.reply(200,self.apitoken_action(s,data))
            if self.path=='/api/admin/action' and data.get('op')=='reports':
                client,token,scope=self.admin_session(s)
                audit=getattr(self.server,'audit',None)
                if not audit: raise APIError('Reports are not switched on for this server.',503)
                return self.reply(200,audit.report(scope))
            if self.path=='/api/admin/action' and data.get('op') in ('login_host_get','login_host_set','login_host_remove','brand_set'):
                out=self.login_host_action(s,data)
                if data.get('op')!='login_host_get': self.log('admin:'+data['op'],s['user']['email'],out.get('host') or out.get('domain'))
                return self.reply(200,out)
            if self.path=='/api/admin/action':
                client,token,scope=self.admin_session(s)
                provisioner=getattr(self.server,'provisioner',None)
                perms=client.actor_perms(token,s['user']['email'],scope)
                out=client.action(token,data,s['user']['email'],scope,provisioner.token if provisioner else None,perms)
                # what changed and for whom (never the new password or any content); look-ups are not logged
                if data.get('op') not in ('dns_records','list_members','policies_get'):
                    self.log('admin:'+str(data.get('op'))[:40],s['user']['email'],data.get('email') or data.get('alias') or data.get('domain') or data.get('id') or data.get('name') or '')
                return self.reply(200,out)
            if self.path=='/api/send':
                data=self.mention_recipients(s,data)
                started=time.time()
                try: result=self.server.zimbra.write_message(s['token'],data,sender=s['user']['email'])
                except APIError as e:
                    return self.send_failed(s,data,e,started)
                self.log('send',s['user']['email'],n=max(1,sum(len([a for a in re.split(r'[,;\n]+',str(data.get(k,''))) if a.strip()]) for k in ('to','cc','bcc'))))
                try: self.server.zimbra.remember_recipients(s['token'],data,s['user']['email'])
                except APIError: pass  # the message went out; a missed contact is not worth an error
                return self.reply(200,result)
            if self.path=='/api/updates': return self.reply(200,self.post_update(s,data))
            if self.path=='/api/calendar':
                if data.get('op')=='delete': return self.reply(200,self.cal(dcalendar.delete_event,self.server.zimbra,s['token'],data))
                return self.reply(200,self.cal(dcalendar.save_event,self.server.zimbra,s['token'],data,s['user']['email']))
            if self.path=='/api/booking': return self.reply(200,self.save_booking(s,data))
            if self.path=='/api/shine/meeting': return self.reply(200,self.shine_meeting(s,data))
            if self.path=='/api/presence': return self.reply(200,self.presence(s,data))
            if self.path=='/api/people-status': return self.reply(200,self.people_status(s,data))
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
                    self.server.avatars.delete(email); self.tell_shine_photo(email); return self.reply(200,{'ok':True,'version':None})
                ext,raw=decode_image(data.get('image'),('png','jpeg','webp'),MAX_AVATAR_BYTES,'Profile photo')
                version=self.server.avatars.put(email,ext,raw); self.tell_shine_photo(email)
                return self.reply(200,{'ok':True,'version':version})
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
    host=parsed.hostname or ''
    server.admin_origin=(os.environ.get('ADMIN_ORIGIN') or (f'{parsed.scheme}://admin-{host}' if host.startswith('mail.') else '')).rstrip('/') or None
    server.appearance=AppearanceStore(os.environ.get('APPEARANCE_DB') or (str(Path(os.environ['SESSION_DB']).with_name('appearance.sqlite')) if os.environ.get('SESSION_DB') else None))
    url=os.environ.get('ZIMBRA_URL'); server.zimbra=Zimbra(url) if url else None
    server.update_files=AppearanceStore((str(Path(os.environ['SESSION_DB']).with_name('update-files.sqlite')) if os.environ.get('SESSION_DB') else None),'files')
    server.audit=AuditLog(str(Path(os.environ['SESSION_DB']).with_name('audit.sqlite')) if os.environ.get('SESSION_DB') else None)
    server.undelivered=Undelivered()
    server.hosts=AppearanceStore((str(Path(os.environ['SESSION_DB']).with_name('login-hosts.sqlite')) if os.environ.get('SESSION_DB') else None),'hosts')
    server.hosts_file=os.environ.get('CUSTOM_HOSTS_FILE') or (str(Path(os.environ['SESSION_DB']).with_name('custom-hosts.txt')) if os.environ.get('SESSION_DB') else None)
    server.booking=AppearanceStore((str(Path(os.environ['SESSION_DB']).with_name('booking.sqlite')) if os.environ.get('SESSION_DB') else None),'booking')
    server.updates=AppearanceStore((str(Path(os.environ['SESSION_DB']).with_name('updates.sqlite')) if os.environ.get('SESSION_DB') else None),'updates')
    server.ui_settings=AppearanceStore((str(Path(os.environ['SESSION_DB']).with_name('settings.sqlite')) if os.environ.get('SESSION_DB') else None),'ui_settings')
    server.mail_host=os.environ.get('MAIL_HOST') or parsed.hostname
    server.shine_origin=(os.environ.get('SHINE_ORIGIN') or 'https://app.shine.dejoiy.com').rstrip('/')
    server.shine_secret=os.environ.get('SHINE_SSO_SECRET','')
    # Joi, DEJOIY's AI buddy, is the assistant here: her page, her API (once her server is up) and the mail app's secret on her admin page
    server.joi_url=(os.environ.get('JOI_URL') or 'https://joi-ai.dejoiy.com').rstrip('/')
    server.joi_api=(os.environ.get('JOI_API_URL') or server.joi_url).rstrip('/')
    server.joi_secret=os.environ.get('JOI_APP_SECRET','')
    server.joi_grant_key=joi_grant_key(str(Path(os.environ['SESSION_DB']).parent) if os.environ.get('SESSION_DB') else None)
    server.joi_internal=[d.strip().lower() for d in (os.environ.get('JOI_INTERNAL_DOMAINS') or 'dejoiy.com,mail.dejoiy.com').split(',') if d.strip()]
    server.shine_site=(os.environ.get('SHINE_SITE') or 'https://convex-site.shine.dejoiy.com').rstrip('/')
    state_dir=Path(os.environ['SESSION_DB']).parent if os.environ.get('SESSION_DB') else None
    # webhooks: signed notes to a company's own tools when something happens (secrets kept 0600 beside the sessions)
    server.hooks=Webhooks(state_dir/'webhooks.json') if state_dir else None
    if server.hooks: server.hooks.start()
    # API tokens for a company's own automation (only their hashes are kept, 0600 beside the sessions)
    server.api_tokens=ApiTokens(state_dir/'api-tokens.json') if state_dir else None
    server.avatars=AvatarStore(str(state_dir/'avatars.sqlite') if state_dir else None)
    server.media=MediaStore(str(state_dir/'media') if state_dir else None)
    if server.zimbra:
        server.zimbra.media_prefix=server.app_origin+'/media/'; server.zimbra.app_url=server.app_origin
        if server.joi_url.startswith('https://'): server.zimbra.joi_images=joi_image_rule(server.joi_url)
    # whose Authentication-Results stamp we trust on incoming mail: our own mail server's name (AUTH_SERVER_ID if it stamps under another)
    if server.zimbra: server.zimbra.authserv=os.environ.get('AUTH_SERVER_ID') or os.environ.get('MAIL_HOST') or urllib.parse.urlsplit(origin).hostname
    admin_url=os.environ.get('ZIMBRA_ADMIN_URL'); server.admin=Admin(admin_url) if admin_url else None
    state=Path(os.environ['SESSION_DB']).parent if os.environ.get('SESSION_DB') else None
    if server.admin:
        server.admin.mail_host=os.environ.get('MAIL_HOST') or urllib.parse.urlsplit(origin).hostname
        server.admin.app_url=server.app_origin
        server.admin.dkim_dir=os.environ.get('DKIM_DIR') or (str(state/'dkim') if state else None)
    server.signups=SignupStore(str(state/'signups.sqlite') if state else None)
    server.reserved_domains={d.strip().lower() for d in os.environ.get('RESERVED_DOMAINS','dejoiy.com').split(',') if d.strip()}
    server.provisioner=Provisioner(server.admin,os.environ['PROVISION_ADMIN'],os.environ['PROVISION_ADMIN_PASSWORD']) if server.admin and os.environ.get('PROVISION_ADMIN') and os.environ.get('PROVISION_ADMIN_PASSWORD') else None
    # 'mail.received' webhooks: incoming mail never passes this server, so a watcher looks once a minute (only for companies that asked)
    # ready-made automations (Configure > Automations), run here on the new-mail watcher
    followup_mail=FollowupMail(server.zimbra,server.provisioner,'no-reply@'+(server.mail_host or 'mail.dejoiy.com')) if server.zimbra and server.provisioner else None
    server.automations=Automations(state_dir/'automations.json',lambda payload: shine_admin_call(server.shine_site,server.shine_secret,payload),server.audit,mail=followup_mail) if state_dir else None
    if server.automations: server.automations.start()
    if (server.hooks or server.automations) and server.provisioner and server.zimbra:
        NewMailWatcher(server.hooks,lambda domain: domain_mailboxes(server.provisioner,domain),
            lambda email: inbox_heads(server.zimbra,delegated_token(server.provisioner,email)),
            listeners=[server.automations] if server.automations else []).start()
    print(f'Dejoiy Mail: {origin}; backend '+('configured' if url else 'requires ZIMBRA_URL'))
    server.serve_forever()

if __name__=='__main__': serve()
