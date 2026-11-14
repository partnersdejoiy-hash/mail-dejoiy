"""Dejoiy Mail Admin, the full mail-server console: Monitor, Manage, Configure, Tools and Search.

Every operation here is a real call to the mail server's admin SOAP API, made with the signed-in
administrator's own admin token, so the mail server checks their rights too. On top of that:
  - company (domain) admins only reach addresses in their own domain, and only with the role
    permission the operation needs (the same PERMISSIONS as the rest of the console);
  - server-wide things (queues, global settings, classes of service, rights, zimlets, certificates,
    caches) are for the Dejoiy platform team only;
  - nothing here deletes mailboxes or mail: there is no purge, no queue delete and no "view mail".
Settings are edited only through allow-lists below, each value checked before it is sent.

This module does not import zimbra.py (that runs as __main__); the caller passes its APIError.
"""
import re
import secrets
import threading
import time
import xml.etree.ElementTree as ET

ADMIN = 'urn:zimbraAdmin'
A = '{'+ADMIN+'}'
UUID = re.compile(r'[a-fA-F0-9-]{36}')
EMAIL = re.compile(r'[^\s<>@,()"\\]+@[^\s<>@,()"\\]+\.[^\s<>@,()"\\]+')
DOMAIN = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')
HOST_PORT = re.compile(r'(?:\[?[a-z0-9.-]{1,253}\]?(?::\d{1,5})?)?')
PASSWORD_MIN = 10


def node(name, attrs=None, text=None):
    e = ET.Element(A+name, attrs or {})
    e.text = text
    return e


def attrs_of(element):
    """Attributes on an admin element; repeated ones (aliases, lists) become lists."""
    out = {}
    for a in element.findall(A+'a'):
        k, v = a.get('n'), a.text or ''
        if k in out:
            out[k] = (out[k] if isinstance(out[k], list) else [out[k]])+[v]
        else:
            out[k] = v
    return out


# ---------- what may be edited, and how each value is checked ----------
# kind: bool | int(lo,hi) | mb(lo,hi) stored as bytes | text(max) | choice(values) | days/hours/minutes(lo,hi) as Zimbra durations
B = ('bool',)
def I(lo, hi): return ('int', lo, hi)
def MB(lo, hi): return ('mb', lo, hi)
def T(n): return ('text', n)
def C(*v): return ('choice', v)
def D(lo, hi): return ('days', lo, hi)
def H(lo, hi): return ('hours', lo, hi)
def M(lo, hi): return ('minutes', lo, hi)

FEATURES = {
    'zimbraFeatureMailEnabled': B, 'zimbraFeatureCalendarEnabled': B, 'zimbraFeatureContactsEnabled': B, 'zimbraFeatureTasksEnabled': B,
    'zimbraFeatureBriefcasesEnabled': B, 'zimbraFeatureFiltersEnabled': B, 'zimbraFeatureMailForwardingEnabled': B,
    'zimbraFeatureOutOfOfficeReplyEnabled': B, 'zimbraFeatureIdentitiesEnabled': B, 'zimbraFeatureSharingEnabled': B,
    'zimbraFeatureChangePasswordEnabled': B, 'zimbraFeatureGalEnabled': B, 'zimbraFeatureSavedSearchesEnabled': B,
    'zimbraFeatureTaggingEnabled': B, 'zimbraImapEnabled': B, 'zimbraPop3Enabled': B,
    'zimbraFeatureTwoFactorAuthAvailable': B, 'zimbraFeatureTwoFactorAuthRequired': B,
}
PASSWORD_RULES = {
    'zimbraPasswordMinLength': I(PASSWORD_MIN, 64), 'zimbraPasswordMaxAge': I(0, 3650), 'zimbraPasswordMinAge': I(0, 3650),
    'zimbraPasswordEnforceHistory': I(0, 24), 'zimbraPasswordLockoutEnabled': B, 'zimbraPasswordLockoutMaxFailures': I(3, 100),
    'zimbraPasswordLockoutDuration': M(5, 1440),
}
LIMITS = {'zimbraMailQuota': MB(0, 10485760), 'zimbraContactMaxNumEntries': I(0, 1000000), 'zimbraAuthTokenLifetime': H(1, 720)}
ACCOUNT_ATTRS = {
    'displayName': T(200), 'givenName': T(100), 'sn': T(100), 'title': T(64), 'company': T(100), 'telephoneNumber': T(40),
    'mobile': T(40), 'description': T(500), 'zimbraHideInGal': B, 'zimbraPasswordMustChange': B, 'zimbraPasswordLocked': B,
    'zimbraPrefOutOfOfficeReplyEnabled': B, 'zimbraPrefOutOfOfficeReply': T(4000), 'zimbraPrefLocale': C('', 'en', 'en_US', 'en_GB', 'hi'),
    **FEATURES, **PASSWORD_RULES, **LIMITS,
}
COS_ATTRS = {'description': T(500), **FEATURES, **PASSWORD_RULES, **LIMITS}
DOMAIN_ATTRS = {'description': T(200), 'zimbraGalMaxResults': I(1, 10000)}
DOMAIN_PLATFORM_ATTRS = {'zimbraDomainMaxAccounts': I(0, 1000000), 'zimbraDomainAggregateQuota': MB(0, 104857600),
    'zimbraPublicServiceHostname': T(253), 'zimbraDomainDefaultCOSId': T(36)}
LIST_ATTRS = {'displayName': T(200), 'description': T(500), 'zimbraHideInGal': B, 'zimbraMailStatus': C('enabled', 'disabled'),
    'zimbraDistributionListSubscriptionPolicy': C('ACCEPT', 'APPROVAL', 'REJECT'),
    'zimbraDistributionListUnsubscriptionPolicy': C('ACCEPT', 'APPROVAL', 'REJECT'),
    'zimbraDistributionListSendShareMessageToNewMembers': B}
RESOURCE_ATTRS = {'displayName': T(200), 'description': T(500), 'zimbraCalResCapacity': I(0, 10000), 'zimbraCalResLocationDisplayName': T(200),
    'zimbraCalResContactName': T(200), 'zimbraCalResContactEmail': T(320), 'zimbraCalResContactPhone': T(40),
    'zimbraCalResAutoAcceptDecline': B, 'zimbraCalResAutoDeclineIfBusy': B, 'zimbraCalResAutoDeclineRecurring': B,
    'zimbraCalResMaxNumConflictsAllowed': I(0, 100), 'zimbraHideInGal': B}
CONFIG_ATTRS = {
    # the message and upload size limits live in one place only: the Settings card (op settings_update)
    'zimbraAttachmentsBlocked': B,
    'zimbraAttachmentsViewInHtmlOnly': B, 'zimbraMtaBlockedExtensionWarnRecipient': B, 'zimbraMtaRelayHost': T(260),
    'zimbraMtaTlsAuthOnly': B, 'zimbraImapCleartextLoginEnabled': B, 'zimbraPop3CleartextLoginEnabled': B,
    'zimbraSpamKillPercent': I(1, 100), 'zimbraSpamTagPercent': I(1, 100), 'zimbraSpamSubjectTag': T(30),
    'zimbraVirusWarnAdmin': B, 'zimbraVirusWarnRecipient': B, 'zimbraVirusBlockEncryptedArchive': B,
    'zimbraVirusDefinitionsUpdateFrequency': C('1h', '2h', '4h', '8h', '12h', '24h'),
    'zimbraSmtpSendAddOriginatingIP': B, 'zimbraGalMaxResults': I(1, 10000),
    'zimbraDefaultDomainName': T(253),
}
SERVER_STATS = ('heap_used', 'heap_free', 'http_threads', 'imap_conn', 'imap_ssl_conn', 'lmtp_rcvd_msgs', 'lmtp_dlvd_msgs',
    'lmtp_rcvd_bytes', 'lmtp_dlvd_bytes', 'mbox_cache', 'mbox_get_count', 'db_conn_count', 'soap_count', 'soap_ms_avg',
    'pop_conn', 'pop_ssl_conn', 'soap_sessions', 'imap_count', 'idx_bytes_written')
QUEUES = ('deferred', 'incoming', 'active', 'hold', 'corrupt')
SESSION_TYPES = ('soap', 'imap', 'admin')
FLUSH_TYPES = ('account', 'cos', 'domain', 'config', 'galgroup', 'group', 'zimlet', 'skin', 'locale', 'server')
GRANT_TARGETS = ('domain', 'dl', 'account', 'cos', 'global')
SEARCH_TYPES = {'accounts': 'account', 'aliases': 'alias', 'distributionlists': 'dl', 'resources': 'calresource', 'domains': 'domain'}

# what a company admin's role must allow (None: platform team only; omitted: look-up open to every company admin)
OP_PERMS = {
    'z_account': 'mailboxes.manage', 'z_account_update': 'mailboxes.manage', 'z_account_rename': 'mailboxes.manage',
    'z_account_signout': 'mailboxes.manage', 'z_reindex': 'mailboxes.manage', 'z_recalc': 'mailboxes.manage',
    'z_resources': 'mailboxes.manage', 'z_resource_create': 'mailboxes.manage', 'z_resource_update': 'mailboxes.manage',
    'z_list': 'teams.manage', 'z_list_update': 'teams.manage', 'z_list_owner': 'teams.manage', 'z_list_rename': 'teams.manage',
    'z_domain': 'domain.view', 'z_domain_update': 'roles.manage', 'z_search': 'mailboxes.manage', 'z_sessions': 'mailboxes.manage',
    'z_overview': None, 'z_server_stats': None, 'z_queues': None, 'z_queue': None, 'z_queue_action': None,
    'z_config': None, 'z_config_update': None, 'z_cos': None, 'z_cos_update': None, 'z_cos_create': None, 'z_cos_copy': None,
    'z_admins': None, 'z_grants': None, 'z_grant': None, 'z_rights': None, 'z_zimlets': None, 'z_zimlet_status': None,
    'z_certs': None, 'z_retention': None, 'z_flush_cache': None,
    'z_undelivered': 'mailboxes.manage',
}
LOOKUPS = {'z_account', 'z_resources', 'z_list', 'z_domain', 'z_search', 'z_sessions', 'z_overview', 'z_server_stats', 'z_queues',
    'z_queue', 'z_config', 'z_cos', 'z_admins', 'z_grants', 'z_rights', 'z_zimlets', 'z_certs', 'z_retention', 'z_undelivered'}

# why a web send was refused, in plain words, for the Undelivered mail page
SEND_FAILURE_REASONS = {
    'mail.MESSAGE_TOO_BIG': 'Mail size limit se badi thi', 'upload_too_big': 'Attachment upload limit se bada tha',
    'mail.SEND_ABORTED_ADDRESS_FAILURE': 'Recipient address mail server ne nahi maana',
    'mail.SEND_PARTIAL_ADDRESS_FAILURE': 'Kuch recipient address mail server ne nahi maane',
    'mail.QUOTA_EXCEEDED': 'Bhejne wale ka mailbox bhara hua tha', 'transport': 'Mail server ne jawab nahi diya',
    'mail.TRY_AGAIN': 'Mail server busy tha', 'service.TRY_AGAIN': 'Mail server busy tha',
}

PERMISSION_NAMES = {'mailboxes.manage': 'Add and edit mailboxes', 'teams.manage': 'Manage departments and team lists',
    'domain.view': 'See the DNS setup', 'roles.manage': 'Manage roles, permissions and the company box'}


def is_console_op(op):
    return isinstance(op, str) and op in OP_PERMS


def clean_value(name, kind, value, Error):
    """The value as the mail server stores it, or Error with a plain message."""
    label = name
    if kind[0] == 'bool':
        if not isinstance(value, bool): raise Error(f'{label} must be on or off.')
        return 'TRUE' if value else 'FALSE'
    if kind[0] in ('int', 'mb', 'days', 'hours', 'minutes'):
        if isinstance(value, bool) or not isinstance(value, int) or not kind[1] <= value <= kind[2]:
            raise Error(f'{label} must be a whole number from {kind[1]} to {kind[2]}.')
        return {'int': str(value), 'mb': str(value*1048576), 'days': f'{value}d', 'hours': f'{value}h', 'minutes': f'{value}m'}[kind[0]]
    if kind[0] == 'text':
        if not isinstance(value, str) or len(value) > kind[1] or any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise Error(f'{label} must be text of up to {kind[1]} characters.')
        return value.strip()
    if kind[0] == 'choice':
        if value not in kind[1]: raise Error(f'{label} must be one of: '+', '.join(x or '(none)' for x in kind[1])+'.')
        return value
    raise Error('Unsupported setting.')


def read_value(kind, raw):
    """A stored value as the console shows it (the reverse of clean_value)."""
    if raw is None or raw == '': return None if kind[0] != 'text' else ''
    if isinstance(raw, list): raw = raw[0]
    if kind[0] == 'bool': return raw.upper() == 'TRUE'
    if kind[0] == 'mb':
        try: return int(raw)//1048576
        except ValueError: return None
    if kind[0] == 'int':
        try: return int(raw)
        except ValueError: return None
    if kind[0] in ('days', 'hours', 'minutes'):
        m = re.fullmatch(r'(\d+)([smhd]?)', raw.strip())
        if not m: return None
        seconds = int(m.group(1))*{'': 1, 's': 1, 'm': 60, 'h': 3600, 'd': 86400}[m.group(2)]
        return seconds//{'days': 86400, 'hours': 3600, 'minutes': 60}[kind[0]]
    return raw


def shown(allowed, a):
    return {k: read_value(kind, a.get(k)) for k, kind in allowed.items()}


def changes(allowed, given, Error):
    if not isinstance(given, dict) or not given: raise Error('Choose a setting to change.')
    unknown = [k for k in given if k not in allowed]
    if unknown: raise Error('These settings cannot be changed here: '+', '.join(sorted(unknown)[:5]))
    return [(k, clean_value(k, allowed[k], v, Error)) for k, v in sorted(given.items())]


def ldap_escape(value):
    return ''.join('\\%02x' % ord(c) if c in '\\*()\x00' else c for c in value)


# certificates are server-wide and change every few weeks: one shared copy, one read at a time
CERTS = {'lock': threading.Lock(), 'certs': None, 'at': 0.0, 'worker': None, 'error': None}
CERT_TTL, CERT_WAIT, CERT_TIMEOUT = 3600, 20, 90
CERT_TYPES = ('mailboxd', 'mta', 'proxy', 'ldap')


class Console:
    """One request's worth of console work for one administrator."""

    def __init__(self, client, token, actor, scope, perms, Error, global_admin=None):
        self.client, self.token, self.actor, self.scope, self.perms, self.Error = client, token, actor.lower(), scope, perms, Error
        self.global_admin = global_admin  # callable: raises unless the actor is a full administrator

    # ----- plumbing -----
    def call(self, request, timeout=None):
        return self.client.call(request, self.token, timeout=timeout) if timeout else self.client.call(request, self.token)

    def own(self, address):
        address = (address or '').lower()
        if self.scope and not address.endswith('@'+self.scope): raise self.Error('You can only manage addresses in '+self.scope+'.', 403)
        return address

    def own_domain(self, domain):
        domain = (domain or '').strip().lower()
        if not DOMAIN.fullmatch(domain): raise self.Error('Enter a valid domain name.')
        if self.scope and domain != self.scope: raise self.Error('You can only manage your own company.', 403)
        return domain

    def ident(self, data, what='mailbox'):
        value = str(data.get('id', ''))
        if not UUID.fullmatch(value): raise self.Error(f'Invalid {what} selection.')
        return value

    def account(self, ident):
        r = node('GetAccountRequest'); r.append(node('account', {'by': 'id'}, ident))
        found = self.call(r).find(A+'account')
        if found is None: raise self.Error('Mailbox not found.', 404)
        self.own(found.get('name'))
        return found

    def modify(self, request_name, ident, pairs, id_as_attr=False):
        r = node(request_name, {'id': ident} if id_as_attr else None)
        if not id_as_attr: r.append(node('id', text=ident))
        for k, v in pairs: r.append(node('a', {'n': k}, v))
        self.call(r)

    def run(self, data):
        op = data.get('op')
        if op not in OP_PERMS: raise self.Error('Unsupported administration operation.')
        need = OP_PERMS[op]
        if self.scope:
            if need is None: raise self.Error('This is managed by the Dejoiy platform team.', 403)
            if self.perms is not None and need not in self.perms:
                raise self.Error(f'Your role does not allow this. Ask an admin for "{PERMISSION_NAMES.get(need, need)}".', 403)
        return getattr(self, op)(data)

    # ----- Monitor -----
    def z_overview(self, data):
        info = self.call(node('GetVersionInfoRequest')).find(A+'info')
        servers = []
        for s in self.call(node('GetAllServersRequest')).findall(A+'server'):
            a = attrs_of(s); services = a.get('zimbraServiceEnabled') or []
            servers.append({'id': s.get('id'), 'name': s.get('name'), 'services': services if isinstance(services, list) else [services]})
        status = [{'server': x.get('server'), 'service': x.get('service'), 'running': (x.text or '').strip() == '1', 'time': x.get('t')}
            for x in self.call(node('GetServiceStatusRequest')).findall('.//'+A+'status')]
        stats = self.call(node('GetMailboxStatsRequest')).find(A+'stats')
        return {'version': {'release': info.get('version', '').split('_')[0] if info is not None else '', 'edition': info.get('type', '') if info is not None else '',
                'built': info.get('buildDate', '') if info is not None else ''},
            'servers': servers, 'status': status,
            'mailboxes': {'count': int(stats.get('numMboxes', '0')), 'bytes': int(stats.get('totalSize', '0'))} if stats is not None else None}

    def z_server_stats(self, data):
        values = {s.get('name'): s.text for s in self.call(node('GetServerStatsRequest'))}
        out = {}
        for k in SERVER_STATS:
            try: out[k] = float(values[k]) if '.' in (values.get(k) or '') else int(values[k])
            except (KeyError, TypeError, ValueError): pass
        return {'stats': out}

    def z_sessions(self, data):
        kind = data.get('type', 'soap')
        if kind not in SESSION_TYPES or (self.scope and kind == 'admin'): raise self.Error('Choose web, IMAP or admin sessions.')
        r = node('GetSessionsRequest', {'type': kind, 'limit': '500', 'refresh': '1', 'sortBy': 'nameAsc'})
        rows = [{'name': s.get('name'), 'created': int(s.get('cd', '0')), 'lastUsed': int(s.get('ld', '0'))} for s in self.call(r).findall(A+'s')]
        if self.scope: rows = [x for x in rows if (x['name'] or '').lower().endswith('@'+self.scope)]
        return {'type': kind, 'sessions': rows}

    def server_name(self, data):
        names = [s.get('name') for s in self.call(node('GetAllServersRequest')).findall(A+'server')]
        name = data.get('server') or (names[0] if names else '')
        if name not in names: raise self.Error('Server not found.', 404)
        return name

    def z_queues(self, data):
        name = self.server_name(data)
        r = node('GetMailQueueInfoRequest'); r.append(node('server', {'name': name}))
        found = self.call(r, timeout=120).find(A+'server')
        return {'server': name, 'queues': [{'name': q.get('name'), 'count': int(q.get('n', '0'))} for q in (found if found is not None else [])]}

    def z_queue(self, data):
        name = self.server_name(data); queue = data.get('queue')
        if queue not in QUEUES: raise self.Error('Choose a mail queue.')
        offset = data.get('offset', 0)
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 100000: raise self.Error('Invalid page.')
        r = node('GetMailQueueRequest'); s = node('server', {'name': name}); q = node('queue', {'name': queue, 'scan': '1', 'wait': '10'})
        q.append(node('query', {'limit': '100', 'offset': str(offset)})); s.append(q); r.append(s)
        found = self.call(r, timeout=120).find('.//'+A+'queue')
        if found is None: return {'queue': queue, 'items': [], 'total': 0, 'more': False}
        items = [{k: i.get(k) for k in ('id', 'from', 'to', 'time', 'size', 'addr', 'reason', 'host', 'filter', 'received', 'origin')} for i in found.findall(A+'qi')]
        summary = {qs.get('type'): [{'value': x.get('t'), 'count': int(x.get('n', '0'))} for x in qs.findall(A+'qsi')][:10] for qs in found.findall(A+'qs')}
        return {'queue': queue, 'items': items, 'summary': summary, 'total': int(found.get('total', '0')), 'more': found.get('more') == '1', 'scanning': found.get('scan') == '1'}

    def z_queue_action(self, data):
        # hold, release and requeue only: messages are never deleted from the console
        name = self.server_name(data); queue = data.get('queue'); action = data.get('action')
        if queue not in QUEUES: raise self.Error('Choose a mail queue.')
        if action not in ('hold', 'release', 'requeue'): raise self.Error('Choose hold, release or requeue.')
        if action == 'release' and queue != 'hold': raise self.Error('Only held messages can be released.')
        ids = data.get('ids')
        if ids == 'all': by, value = 'query', ''
        elif isinstance(ids, list) and 1 <= len(ids) <= 500 and all(isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9]{6,40}', x) for x in ids): by, value = 'id', ','.join(ids)
        else: raise self.Error('Choose the messages to act on.')
        r = node('MailQueueActionRequest'); s = node('server', {'name': name}); q = node('queue', {'name': queue})
        a = node('action', {'op': action, 'by': by}, value or None)
        if by == 'query': a.append(node('query'))
        q.append(a); s.append(q); r.append(s)
        self.call(r, timeout=120)
        return {'ok': True}

    def z_undelivered(self, data):
        """Every message of the last 14 days that was stopped, bounced, rejected or is still waiting, from the
        real mail logs (see undelivered.py), plus web sends the server refused. Company admins: own domain only."""
        source = getattr(self, 'undelivered', None)
        got = source.query(self.scope) if source else {'rows': [], 'indexedAt': None, 'available': False}
        rows = list(got['rows'])
        failed = getattr(self, 'failed_sends', None)
        for f in (failed(self.scope) if failed else []):
            code = f['code']
            rows.append({'ts': f['ts'], 'qid': '', 'from': f['from'], 'to': f['to'] or '', 'outcome': 'refused', 'action': 'kept in Drafts',
                'direction': 'outbound', 'reason': SEND_FAILURE_REASONS.get(code, 'Mail server ne mail nahi li') + (f' ({code})' if code else ''),
                'notified': 'sender (on screen, saved in Drafts)'})
        if self.scope:
            mine = lambda a: (a or '').lower().endswith('@' + self.scope)
            rows = [r for r in rows if mine(r['from']) or any(mine(x) for x in str(r['to']).split(','))]
        rows.sort(key=lambda r: -r['ts'])
        for r in rows: r['at'] = int(r.pop('ts') * 1000)
        counts = {}
        for r in rows: counts[r['outcome']] = counts.get(r['outcome'], 0) + 1
        silent = sum(1 for r in rows if r['notified'] in ('no', 'not yet'))
        return {'rows': rows[:500], 'counts': counts, 'notToldCount': silent, 'indexedAt': got.get('indexedAt'), 'available': got.get('available', False)}

    # ----- Manage: accounts -----
    def z_account(self, data):
        found = self.account(self.ident(data)); a = attrs_of(found)
        member = node('GetAccountMembershipRequest'); member.append(node('account', {'by': 'id'}, found.get('id')))
        try: lists = [{'id': d.get('id'), 'email': d.get('name'), 'via': d.get('via')} for d in self.call(member).findall(A+'dl')]
        except self.Error: lists = []
        size = None
        try:
            box = node('GetMailboxRequest'); box.append(node('mbox', {'id': found.get('id')}))
            m = self.call(box).find(A+'mbox'); size = int(m.get('s', '0')) if m is not None else None
        except self.Error: pass
        aliases = a.get('zimbraMailAlias') or []
        return {'id': found.get('id'), 'email': found.get('name'), 'settings': shown(ACCOUNT_ATTRS, a),
            'status': a.get('zimbraAccountStatus', 'active'), 'cosId': a.get('zimbraCOSId', ''),
            'aliases': aliases if isinstance(aliases, list) else [aliases], 'lists': lists, 'usedBytes': size,
            'created': a.get('zimbraCreateTimestamp', ''), 'lastLogin': a.get('zimbraLastLogonTimestamp', ''),
            'passwordChanged': a.get('zimbraPasswordModifiedTime', ''), 'mailHost': a.get('zimbraMailHost', ''),
            'isAdmin': a.get('zimbraIsAdminAccount') == 'TRUE', 'isDomainAdmin': a.get('zimbraIsDelegatedAdminAccount') == 'TRUE',
            'twoFactor': a.get('zimbraTwoFactorAuthEnabled') == 'TRUE'}

    def z_account_update(self, data):
        found = self.account(self.ident(data))
        pairs = changes(ACCOUNT_ATTRS, data.get('settings'), self.Error)
        if found.get('name', '').lower() == self.actor and any(k in ('zimbraPasswordLocked', 'zimbraFeatureMailEnabled') for k, _ in pairs):
            raise self.Error('You cannot lock yourself out of your own administrator mailbox.')
        self.modify('ModifyAccountRequest', found.get('id'), pairs)
        return {'ok': True, 'changed': [k for k, _ in pairs]}

    def z_account_rename(self, data):
        found = self.account(self.ident(data)); new = str(data.get('email', '')).strip().lower()
        if not EMAIL.fullmatch(new) or len(new) > 320: raise self.Error('Enter the new mailbox address.')
        self.own(new)
        if found.get('name', '').lower() == self.actor: raise self.Error('You cannot rename the mailbox you are signed in with.')
        self.call(node('RenameAccountRequest', {'id': found.get('id'), 'newName': new}))
        return {'ok': True, 'email': new}

    def z_account_signout(self, data):
        # the console's "sign out everywhere": every token issued before now stops working
        found = self.account(self.ident(data))
        try: current = int(attrs_of(found).get('zimbraAuthTokenValidityValue') or '0')
        except ValueError: current = 0
        self.modify('ModifyAccountRequest', found.get('id'), [('zimbraAuthTokenValidityValue', str((current+1) % 2147483647))])
        return {'ok': True}

    # ----- Manage: resources (rooms and equipment) -----
    def z_resources(self, data):
        r = node('GetAllCalendarResourcesRequest')
        if self.scope: r.append(node('domain', {'by': 'name'}, self.scope))
        out = []
        for c in self.call(r).findall(A+'calresource'):
            a = attrs_of(c)
            out.append({'id': c.get('id'), 'email': c.get('name'), 'type': a.get('zimbraCalResType', ''), 'status': a.get('zimbraAccountStatus', 'active'),
                **shown(RESOURCE_ATTRS, a)})
        return {'resources': out}

    def z_resource_create(self, data):
        email = self.own(str(data.get('email', '')).strip())
        if not EMAIL.fullmatch(email) or len(email) > 320: raise self.Error('Enter the resource address, like room1@yourcompany.com.')
        kind = data.get('type')
        if kind not in ('Location', 'Equipment'): raise self.Error('Choose a room (Location) or equipment.')
        settings = dict(data.get('settings') or {})
        if not str(settings.get('displayName', '')).strip(): raise self.Error('Give the resource a name.')
        pairs = changes(RESOURCE_ATTRS, settings, self.Error)
        r = node('CreateCalendarResourceRequest'); r.append(node('name', text=email))
        r.append(node('password', text=secrets.token_urlsafe(24)))  # nobody signs in as a room; Zimbra still wants one
        r.append(node('a', {'n': 'zimbraCalResType'}, kind)); r.append(node('a', {'n': 'zimbraAccountStatus'}, 'active'))
        for k, v in pairs: r.append(node('a', {'n': k}, v))
        created = self.call(r).find(A+'calresource')
        return {'ok': True, 'id': created.get('id') if created is not None else ''}

    def resource(self, ident):
        r = node('GetCalendarResourceRequest'); r.append(node('calresource', {'by': 'id'}, ident))
        found = self.call(r).find(A+'calresource')
        if found is None: raise self.Error('Resource not found.', 404)
        self.own(found.get('name'))
        return found

    def z_resource_update(self, data):
        found = self.resource(self.ident(data, 'resource'))
        settings = dict(data.get('settings') or {}); extra = []
        status = settings.pop('status', None)
        if status is not None:
            if status not in ('active', 'closed', 'maintenance'): raise self.Error('A resource can be active, closed or under maintenance.')
            extra.append(('zimbraAccountStatus', status))
        pairs = (changes(RESOURCE_ATTRS, settings, self.Error) if settings else [])+extra
        if not pairs: raise self.Error('Choose a setting to change.')
        self.modify('ModifyCalendarResourceRequest', found.get('id'), pairs)
        return {'ok': True}

    # ----- Manage: distribution lists -----
    def dl(self, ident, limit='0'):
        r = node('GetDistributionListRequest', {'limit': limit}); r.append(node('dl', {'by': 'id'}, ident))
        found = self.call(r).find(A+'dl')
        if found is None: raise self.Error('Mailing list not found.', 404)
        self.own(found.get('name'))
        return found

    def z_list(self, data):
        found = self.dl(self.ident(data, 'mailing list')); a = attrs_of(found)
        owners = [o.get('name') for o in found.findall('.//'+A+'owner') if o.get('name')]
        return {'id': found.get('id'), 'email': found.get('name'), 'settings': shown(LIST_ATTRS, a),
            'members': sorted(m.text for m in found.findall(A+'dlm') if m.text), 'owners': owners,
            'aliases': [x for x in ([a['zimbraMailAlias']] if isinstance(a.get('zimbraMailAlias'), str) else a.get('zimbraMailAlias') or []) if x]}

    def z_list_update(self, data):
        found = self.dl(self.ident(data, 'mailing list'), '1')
        pairs = changes(LIST_ATTRS, data.get('settings'), self.Error)
        self.modify('ModifyDistributionListRequest', found.get('id'), pairs)
        return {'ok': True}

    def z_list_owner(self, data):
        found = self.dl(self.ident(data, 'mailing list'), '1')
        owner = str(data.get('owner', '')).strip().lower()
        if not EMAIL.fullmatch(owner): raise self.Error('Enter the owner\'s address.')
        self.own(owner)
        r = node('RevokeRightRequest' if data.get('remove') is True else 'GrantRightRequest')
        r.append(node('target', {'type': 'dl', 'by': 'id'}, found.get('id')))
        r.append(node('grantee', {'type': 'usr', 'by': 'name'}, owner)); r.append(node('right', text='ownDistList'))
        self.call(r)
        return {'ok': True}

    def z_list_rename(self, data):
        found = self.dl(self.ident(data, 'mailing list'), '1')
        new = str(data.get('email', '')).strip().lower()
        if not EMAIL.fullmatch(new): raise self.Error('Enter the new list address.')
        self.own(new)
        r = node('RenameDistributionListRequest', {'id': found.get('id'), 'newName': new})
        self.call(r)
        return {'ok': True, 'email': new}

    # ----- Manage / Configure: domains -----
    def domain(self, name):
        r = node('GetDomainRequest'); r.append(node('domain', {'by': 'name'}, name))
        found = self.call(r).find(A+'domain')
        if found is None: raise self.Error('Domain not found.', 404)
        return found

    def z_domain(self, data):
        name = self.own_domain(data.get('domain')); found = self.domain(name); a = attrs_of(found)
        count = None
        try:
            c = node('CountAccountRequest'); c.append(node('domain', {'by': 'name'}, name))
            count = [{'cosId': x.get('id'), 'cos': x.get('name'), 'count': int(x.text or '0')} for x in self.call(c).findall(A+'cos')]
        except self.Error: pass
        hosts = a.get('zimbraVirtualHostname') or []
        return {'id': found.get('id'), 'domain': name, 'settings': shown(DOMAIN_ATTRS, a),
            'platform': None if self.scope else shown(DOMAIN_PLATFORM_ATTRS, a),
            'status': a.get('zimbraDomainStatus', 'active'), 'virtualHosts': hosts if isinstance(hosts, list) else [hosts], 'accountsByCos': count}

    def z_domain_update(self, data):
        name = self.own_domain(data.get('domain')); found = self.domain(name)
        allowed = DOMAIN_ATTRS if self.scope else {**DOMAIN_ATTRS, **DOMAIN_PLATFORM_ATTRS}
        pairs = changes(allowed, data.get('settings'), self.Error)
        for k, v in pairs:
            if k == 'zimbraDomainDefaultCOSId' and v and not UUID.fullmatch(v): raise self.Error('Choose a class of service.')
            if k == 'zimbraPublicServiceHostname' and v and not DOMAIN.fullmatch(v): raise self.Error('Enter a host name like mail.example.com.')
        self.modify('ModifyDomainRequest', found.get('id'), pairs)
        return {'ok': True}

    # ----- Search -----
    def z_search(self, data):
        text = str(data.get('text', '')).strip()[:100]
        types = data.get('types') or ['accounts']
        if not isinstance(types, list) or not types or any(t not in SEARCH_TYPES for t in types): raise self.Error('Choose what to search.')
        if self.scope and 'domains' in types: raise self.Error('Search within your own company.', 403)
        status = data.get('status', '')
        if status not in ('', 'active', 'locked', 'closed', 'maintenance', 'lockout', 'pending'): raise self.Error('Choose a status.')
        offset = data.get('offset', 0)
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 100000: raise self.Error('Invalid page.')
        domain = self.scope or (str(data.get('domain', '')).strip().lower() or None)
        if domain and not DOMAIN.fullmatch(domain): raise self.Error('Enter a valid domain name.')
        parts = []
        if text:
            t = ldap_escape(text)
            parts.append(f'(|(mail=*{t}*)(cn=*{t}*)(sn=*{t}*)(givenName=*{t}*)(displayName=*{t}*)(zimbraMailAlias=*{t}*)(zimbraDomainName=*{t}*)(uid=*{t}*))')
        if status: parts.append(f'(zimbraAccountStatus={status})')
        # the mail server's own system mailboxes (spam training, quarantine, directory sync) are never
        # listed, so leave them out of the search itself: the count then matches the rows shown
        parts.append('(!(zimbraIsSystemResource=TRUE))')
        query = '(&'+''.join(parts)+')'
        r = node('SearchDirectoryRequest', {'query': query, 'limit': '50', 'offset': str(offset), 'types': ','.join(types),
            'sortBy': 'name', 'sortAscending': '1', 'countOnly': '0',
            'attrs': 'displayName,zimbraAccountStatus,zimbraLastLogonTimestamp,zimbraMailQuota,zimbraCalResType,zimbraIsSystemResource,zimbraAliasTargetId,zimbraDomainStatus'})
        if domain: r.set('domain', domain)
        out = self.call(r); rows = []; dropped = 0
        for e in out:
            kind = e.tag.split('}')[1]
            a = attrs_of(e)
            if kind not in SEARCH_TYPES.values() or a.get('zimbraIsSystemResource') == 'TRUE':
                dropped += 1; continue
            rows.append({'kind': kind, 'id': e.get('id'), 'name': e.get('name'), 'displayName': a.get('displayName', ''),
                'status': a.get('zimbraAccountStatus') or a.get('zimbraDomainStatus') or '', 'lastLogin': a.get('zimbraLastLogonTimestamp', ''),
                'target': e.get('targetName') or '', 'type': a.get('zimbraCalResType', '')})
        return {'results': rows, 'total': max(len(rows)+offset, int(out.get('searchTotal', len(rows)))-dropped), 'more': out.get('more') in ('1', 'true')}

    # ----- Configure: classes of service -----
    def z_cos(self, data):
        out = []
        for c in self.call(node('GetAllCosRequest')).findall(A+'cos'):
            out.append({'id': c.get('id'), 'name': c.get('name'), 'settings': shown(COS_ATTRS, attrs_of(c))})
        return {'cos': out}

    def z_cos_update(self, data):
        ident = self.ident(data, 'class of service')
        pairs = changes(COS_ATTRS, data.get('settings'), self.Error)
        self.modify('ModifyCosRequest', ident, pairs)
        return {'ok': True}

    def cos_name(self, data):
        name = str(data.get('name', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,59}', name): raise self.Error('Use 1 to 60 letters, numbers, spaces, dots, dashes or underscores.')
        return name

    def z_cos_create(self, data):
        r = node('CreateCosRequest'); r.append(node('name', text=self.cos_name(data)))
        found = self.call(r).find(A+'cos')
        return {'ok': True, 'id': found.get('id') if found is not None else ''}

    def z_cos_copy(self, data):
        ident = self.ident(data, 'class of service')
        r = node('CopyCosRequest'); r.append(node('name', text=self.cos_name(data))); r.append(node('cos', {'by': 'id'}, ident))
        found = self.call(r).find(A+'cos')
        return {'ok': True, 'id': found.get('id') if found is not None else ''}

    # ----- Configure: global settings -----
    def z_config(self, data):
        a = attrs_of(self.call(node('GetAllConfigRequest')))
        return {'settings': shown(CONFIG_ATTRS, a)}

    def z_config_update(self, data):
        if self.global_admin: self.global_admin()
        pairs = changes(CONFIG_ATTRS, data.get('settings'), self.Error)
        for k, v in pairs:
            if k == 'zimbraMtaRelayHost' and v and not HOST_PORT.fullmatch(v.lower()): raise self.Error('Relay host must look like smtp.example.com:587, or be empty.')
            if k == 'zimbraDefaultDomainName' and not DOMAIN.fullmatch(v): raise self.Error('Choose one of your domains.')
        r = node('ModifyConfigRequest')
        for k, v in pairs: r.append(node('a', {'n': k}, v))
        self.call(r)
        return {'ok': True, 'changed': [k for k, _ in pairs]}

    # ----- Configure: administrators and rights -----
    def z_admins(self, data):
        out = []
        for e in self.call(node('GetAllAdminAccountsRequest')).findall(A+'account'):
            a = attrs_of(e)
            out.append({'id': e.get('id'), 'email': e.get('name'), 'name': a.get('displayName', ''), 'status': a.get('zimbraAccountStatus', 'active'),
                'global': a.get('zimbraIsAdminAccount') == 'TRUE', 'delegated': a.get('zimbraIsDelegatedAdminAccount') == 'TRUE'})
        return {'admins': out}

    def z_rights(self, data):
        rights = [{'name': r.get('name'), 'type': r.get('type'), 'target': r.get('targetType', ''),
            'description': (r.findtext(A+'desc') or '')[:200]} for r in self.call(node('GetAllRightsRequest', {'expandAllAttrs': '0'})).findall(A+'right')]
        return {'rights': sorted(rights, key=lambda r: r['name'] or '')}

    def z_grants(self, data):
        email = str(data.get('email', '')).strip().lower()
        if not EMAIL.fullmatch(email): raise self.Error('Choose an administrator.')
        r = node('GetGrantsRequest'); r.append(node('grantee', {'type': 'usr', 'by': 'name', 'all': '1'}, email))
        out = []
        for g in self.call(r).findall(A+'grant'):
            t, ge, ri = g.find(A+'target'), g.find(A+'grantee'), g.find(A+'right')
            out.append({'target': {'type': t.get('type'), 'name': t.get('name')} if t is not None else None,
                'grantee': ge.get('name') if ge is not None else '', 'right': ri.text if ri is not None else '',
                'deny': ri is not None and ri.get('deny') == '1', 'canDelegate': ri is not None and ri.get('canDelegate') == '1'})
        return {'email': email, 'grants': out}

    def z_grant(self, data):
        if self.global_admin: self.global_admin()
        target_type = data.get('targetType'); target = str(data.get('target', '')).strip().lower()
        if target_type not in GRANT_TARGETS: raise self.Error('Choose what the right applies to.')
        if target_type == 'domain' and not DOMAIN.fullmatch(target): raise self.Error('Enter a domain.')
        if target_type in ('dl', 'account') and not EMAIL.fullmatch(target): raise self.Error('Enter an address.')
        if target_type == 'cos' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,59}', target): raise self.Error('Enter a class of service name.')
        grantee = str(data.get('grantee', '')).strip().lower()
        if not EMAIL.fullmatch(grantee): raise self.Error('Enter the administrator\'s address.')
        if grantee == self.actor: raise self.Error('You cannot change your own rights.')
        right = str(data.get('right', ''))
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9.]{1,80}', right) or right not in {x['name'] for x in self.z_rights({})['rights']}: raise self.Error('Choose a right from the list.')
        if data.get('revoke') is not True:
            # the mail server only gives admin rights to delegated administrators (not to ordinary
            # mailboxes, and not to platform admins, who already have every right)
            look = node('GetAccountRequest', {'attrs': 'zimbraIsDelegatedAdminAccount,zimbraIsAdminAccount'}); look.append(node('account', {'by': 'name'}, grantee))
            found = self.call(look).find(A+'account')
            if found is None: raise self.Error('No mailbox has that address.', 404)
            a = attrs_of(found)
            if a.get('zimbraIsAdminAccount') == 'TRUE': raise self.Error(grantee+' is a platform admin and already has every right.')
            if a.get('zimbraIsDelegatedAdminAccount') != 'TRUE':
                raise self.Error(grantee+' is not an administrator yet. Make them a company admin first (Accounts, Access), then give rights here.')
        r = node('RevokeRightRequest' if data.get('revoke') is True else 'GrantRightRequest')
        r.append(node('target', {'type': target_type, **({'by': 'name'} if target_type != 'global' else {})}, target if target_type != 'global' else 'globalacltarget'))
        r.append(node('grantee', {'type': 'usr', 'by': 'name'}, grantee))
        r.append(node('right', {**({'deny': '1'} if data.get('deny') is True else {}), **({'canDelegate': '1'} if data.get('canDelegate') is True else {})}, right))
        self.call(r)
        return {'ok': True}

    # ----- Configure: zimlets, certificates, retention -----
    def z_zimlets(self, data):
        out = []
        for z in self.call(node('GetAllZimletsRequest')).findall(A+'zimlet'):
            a = attrs_of(z)
            out.append({'name': z.get('name'), 'enabled': a.get('zimbraZimletEnabled', 'TRUE') == 'TRUE',
                'extension': a.get('zimbraZimletIsExtension') == 'TRUE', 'description': '' if str(a.get('zimbraZimletDescription', '')).startswith('${') else a.get('zimbraZimletDescription', '')})
        return {'zimlets': sorted(out, key=lambda x: x['name'] or '')}

    def z_zimlet_status(self, data):
        name = str(data.get('name', ''))
        if name not in {z['name'] for z in self.z_zimlets({})['zimlets']}: raise self.Error('Zimlet not found.', 404)
        r = node('ModifyZimletRequest'); z = node('zimlet', {'name': name})
        z.append(node('status', {'value': 'enabled' if data.get('enabled') is True else 'disabled'})); r.append(z)
        self.call(r)
        return {'ok': True}

    def z_certs(self, data):
        """The certificates, read at most once an hour. The mail server reads each one over its own
        remote-management link (about 8 s), so the read runs in one background
        thread at a time and a request waits at most CERT_WAIT seconds; the page asks again."""
        with CERTS['lock']:
            fresh = CERTS['certs'] is not None and time.time()-CERTS['at'] < CERT_TTL and data.get('refresh') is not True
            start = not fresh and not (CERTS['worker'] and CERTS['worker'].is_alive())
        if start:
            sid = next((s.get('id') for s in self.call(node('GetAllServersRequest')).findall(A+'server')), None)
            if not sid: raise self.Error('Server not found.', 404)
        with CERTS['lock']:
            if start and not (CERTS['worker'] and CERTS['worker'].is_alive()):
                CERTS['error'] = None
                CERTS['worker'] = threading.Thread(target=self._read_certs, args=(sid,), daemon=True, name='console-certs')
                CERTS['worker'].start()
            worker = CERTS['worker']
        if not fresh and worker: worker.join(CERT_WAIT)
        with CERTS['lock']:
            busy = bool(CERTS['worker'] and CERTS['worker'].is_alive())
            if CERTS['error'] and not busy and CERTS['certs'] is None: raise self.Error(CERTS['error'], 502)
            return {'certs': CERTS['certs'] or [], 'checkedAt': int(CERTS['at']*1000) if CERTS['certs'] is not None else None,
                    'pending': busy, 'error': CERTS['error'] if not busy else None}

    def _read_certs(self, sid):
        # one call per kind, side by side: about 8 s in all instead of 26 s for type=all
        found, errors = {}, []
        def one(kind):
            try:
                out = self.call(node('GetCertRequest', {'type': kind, 'option': 'self', 'server': sid}), timeout=CERT_TIMEOUT)
                found[kind] = [{'type': c.get('type'), 'subject': c.findtext(A+'subject') or '', 'issuer': c.findtext(A+'issuer') or '',
                    'notBefore': c.findtext(A+'notBefore') or '', 'notAfter': c.findtext(A+'notAfter') or '',
                    'altNames': c.findtext(A+'SubjectAltName') or ''} for c in out.iter(A+'cert')]
            except Exception as e:  # shown on the page; the request that started this read may be long gone
                errors.append(str(e) if isinstance(e, self.Error) and str(e) else 'The mail server did not return its certificates.')
        readers = [threading.Thread(target=one, args=(k,), daemon=True) for k in CERT_TYPES]
        for t in readers: t.start()
        for t in readers: t.join(CERT_TIMEOUT+5)
        certs = [c for k in CERT_TYPES for c in found.get(k, [])]
        with CERTS['lock']:
            if found: CERTS.update(certs=certs, at=time.time())
            CERTS['error'] = (errors[0] if not found else 'Some certificates could not be read: '+errors[0]) if errors else None

    def z_retention(self, data):
        out = self.call(node('GetSystemRetentionPolicyRequest'))
        def policies(kind):
            return [{'name': p.get('name'), 'lifetime': p.get('lifetime'), 'id': p.get('id')} for e in out.iter() if e.tag.endswith('}'+kind) for p in e if p.tag.endswith('}policy')]
        return {'keep': policies('keep'), 'purge': policies('purge')}

    # ----- Tools -----
    def z_reindex(self, data):
        found = self.account(self.ident(data)); action = data.get('action', 'start')
        if action not in ('start', 'status'): raise self.Error('Choose start or status.')
        r = node('ReIndexRequest', {'action': action}); r.append(node('mbox', {'id': found.get('id')}))
        out = self.call(r)
        progress = out.find(A+'progress')
        return {'status': out.get('status', ''), 'progress': {k: progress.get(k) for k in ('numSucceeded', 'numFailed', 'numRemaining')} if progress is not None else None}

    def z_recalc(self, data):
        found = self.account(self.ident(data))
        r = node('RecalculateMailboxCountsRequest'); r.append(node('mbox', {'id': found.get('id')}))
        m = self.call(r).find(A+'mbox')
        return {'ok': True, 'usedBytes': int(m.get('used', '0')) if m is not None else None}

    def z_flush_cache(self, data):
        kinds = data.get('types')
        if not isinstance(kinds, list) or not kinds or any(k not in FLUSH_TYPES for k in kinds): raise self.Error('Choose which caches to refresh.')
        r = node('FlushCacheRequest'); r.append(node('cache', {'type': ','.join(sorted(set(kinds))), 'allServers': '1'}))
        self.call(r)
        return {'ok': True}
