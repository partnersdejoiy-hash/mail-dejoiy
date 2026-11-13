"""API tokens and the /api/v1 automation API: hashes only, one company never reaches another, bare 401s, limits, audit."""
import io, json, os, stat, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z
import apitokens as at

M = '{urn:zimbraMail}'
A = '{urn:zimbraAdmin}'


def store(clock=None):
    tmp = tempfile.TemporaryDirectory()
    s = at.ApiTokens(Path(tmp.name) / 'api-tokens.json', **({'clock': clock} if clock else {}))
    s._tmp = tmp
    return s


def make(s, domain='acme.com', scopes=('mail.send', 'mail.label', 'mail.read', 'shine.post'), days=30, name=None, actor='boss@acme.com'):
    name = name or 'robot %d' % len(s.all.get(domain, []))
    return s.action('apitoken_add', {'name': name, 'scopes': list(scopes), 'days': days}, domain, actor)['token']


class Store(unittest.TestCase):
    def test_token_shown_once_and_only_its_hash_is_kept(self):
        s = store(); raw = make(s)
        self.assertTrue(raw.startswith('dmk_'))
        text = s.path.read_text()
        self.assertNotIn(raw, text); self.assertNotIn(raw.rsplit('_', 1)[1], text)
        self.assertIn(at.digest(raw), text)
        self.assertEqual(stat.S_IMODE(os.stat(s.path).st_mode), 0o600)
        listed = s.action('apitokens_get', {}, 'acme.com', 'boss@acme.com')
        self.assertNotIn('token', listed)
        self.assertNotIn('hash', json.dumps(listed))
        # survives a restart
        self.assertEqual(at.ApiTokens(s.path).check(raw)['domain'], 'acme.com')

    def test_ten_per_company(self):
        s = store()
        for i in range(10): make(s)
        with self.assertRaisesRegex(at.TokenError, '10'): make(s)
        make(s, domain='other.com')   # another company has its own ten

    def test_what_the_admin_must_choose(self):
        s = store()
        with self.assertRaisesRegex(at.TokenError, 'name'): s.action('apitoken_add', {'name': '', 'scopes': ['mail.send'], 'days': 30}, 'acme.com', 'a@acme.com')
        with self.assertRaisesRegex(at.TokenError, 'permission'): s.action('apitoken_add', {'name': 'x', 'scopes': ['root'], 'days': 30}, 'acme.com', 'a@acme.com')
        with self.assertRaisesRegex(at.TokenError, 'mail.read'): s.action('apitoken_add', {'name': 'x', 'scopes': ['mail.read.body'], 'days': 30}, 'acme.com', 'a@acme.com')
        with self.assertRaisesRegex(at.TokenError, 'how long'): s.action('apitoken_add', {'name': 'x', 'scopes': ['mail.send'], 'days': 5000}, 'acme.com', 'a@acme.com')
        make(s, name='Same')
        with self.assertRaisesRegex(at.TokenError, 'already'): make(s, name='same')

    def test_only_a_live_exact_token_passes(self):
        now = [1000.0]; s = store(lambda: now[0]); raw = make(s, days=7)
        self.assertEqual(s.check(raw)['domain'], 'acme.com')
        self.assertEqual(s.check(' ' + raw + ' ')['domain'], 'acme.com')
        tid = raw.split('_')[1]
        for wrong in ('', 'dmk_', raw[:-1] + ('A' if raw[-1] != 'A' else 'B'), 'dmk_%s_%s' % (tid, 'x' * 43), raw.replace('dmk_', 'whsec_')):
            self.assertIsNone(s.check(wrong), wrong[:12])
        now[0] += 7 * 86400
        self.assertIsNone(s.check(raw))   # expired

    def test_revoke_stops_it_at_once(self):
        s = store(); raw = make(s); tid = raw.split('_')[1]
        out = s.action('apitoken_revoke', {'id': tid}, 'acme.com', 'boss@acme.com')
        self.assertEqual(out['tokens'], [])
        self.assertIsNone(s.check(raw))

    def test_one_company_cannot_revoke_anothers_token(self):
        s = store(); raw = make(s, domain='acme.com'); tid = raw.split('_')[1]
        with self.assertRaisesRegex(at.TokenError, 'no longer'): s.action('apitoken_revoke', {'id': tid}, 'other.com', 'evil@other.com')
        self.assertIsNotNone(s.check(raw))

    def test_rate_limits(self):
        now = [1000.0]; s = store(lambda: now[0])
        self.assertTrue(all(s.allow('t1', 'mail.read') for _ in range(at.PER_MINUTE)))
        self.assertFalse(s.allow('t1', 'mail.read'))
        self.assertTrue(s.allow('t2', 'mail.read'))   # per token
        now[0] += 61
        self.assertTrue(s.allow('t1', 'mail.read'))
        sent = 0
        for _ in range(200):
            now[0] += 1.1   # under the per-minute limit, so only the hourly mail limit stops it
            sent += s.allow('t3', 'mail.send')
        self.assertEqual(sent, at.SENDS_PER_HOUR)


class FakeMail:
    def __init__(self):
        self.calls = []
    def write_message(self, token, data, draft=False, sender=''):
        self.calls.append(('send', token, data, sender)); return {'id': '900', 'accepted': True}
    def action(self, token, data):
        self.calls.append(('label', token, data)); return {'ok': True}
    def call(self, r, token=None, timeout=25):
        self.calls.append(('call', token, r.tag))
        if r.tag == M + 'SearchRequest':
            self.recip = r.get('recip')
            out = ET.Element(M + 'SearchResponse')
            m = ET.SubElement(out, M + 'm', {'id': '361', 'd': '1794600826000', 'f': 'u', 'tn': 'Invoices'})
            ET.SubElement(m, M + 'e', {'t': 'f', 'a': 'x@vendor.com'}); ET.SubElement(m, M + 'e', {'t': 't', 'a': 'test@acme.com'})
            ET.SubElement(m, M + 'su').text = 'Invoice 7'; ET.SubElement(m, M + 'fr').text = 'secret body preview'
            return out
        out = ET.Element(M + 'GetMsgResponse'); m = ET.SubElement(out, M + 'm', {'id': '361'})
        mp = ET.SubElement(m, M + 'mp', {'ct': 'text/plain'}); ET.SubElement(mp, M + 'content').text = 'Please pay.'
        return out


def api(s, method, path, raw=None, body=None, headers=None, missing=()):
    h = object.__new__(z.Handler)
    h.path = path
    h.headers = {**({'Authorization': 'Bearer ' + raw} if raw is not None else {}), **(headers or {})}
    payload = json.dumps(body).encode() if body is not None else b''
    if method == 'POST': h.headers.setdefault('Content-Type', 'application/json'); h.headers['Content-Length'] = str(len(payload))
    h.rfile = io.BytesIO(payload)
    mail = FakeMail(); shine = []; logged = []; delegated = []
    h.server = SimpleNamespace(api_tokens=s, zimbra=mail)
    def deleg(email):
        delegated.append(email)
        if email in missing: raise z.APIError('Mailbox not found.', 502, 'account.NO_SUCH_ACCOUNT')
        return 'tok:' + email
    h.delegated = deleg
    h.shine_admin_post = lambda p: shine.append(p) or {'ok': True, 'channel': p['channel']}
    h.log = lambda kind, actor, target='', n=1: logged.append((kind, actor, target, n))
    out = {}
    def reply(status, data, cookie=None): out.update(status=status, data=data)
    h.reply = reply
    getattr(h, 'do_' + method)()
    return SimpleNamespace(status=out['status'], data=out['data'], mail=mail, shine=shine, logged=logged, delegated=delegated)


class Api(unittest.TestCase):
    def setUp(self):
        self.s = store()
        self.acme = make(self.s, domain='acme.com', actor='boss@acme.com')
        self.other = make(self.s, domain='other.com', actor='chief@other.com')

    def test_every_wrong_token_gets_the_same_bare_401(self):
        expired = store(lambda: 0.0); old = make(expired, days=7)
        cases = [None, '', 'nope', self.acme[:-2] + 'zz', old]
        for raw in cases:
            r = api(self.s, 'POST', '/api/v1/mail/send', raw, {'mailbox': 'test@acme.com', 'to': 'a@b.com', 'text': 'hi'})
            self.assertEqual((r.status, r.data), (401, {'error': 'Unauthorized'}))
            self.assertEqual(r.mail.calls, []); self.assertEqual(r.delegated, []); self.assertEqual(r.logged, [])
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=test@acme.com', 'Basic ' + self.acme)
        self.assertEqual(r.status, 401)
        r = api(self.s, 'GET', '/api/v1/anything', None)
        self.assertEqual((r.status, r.data), (401, {'error': 'Unauthorized'}))   # unknown paths say nothing without a token either

    def test_one_company_token_never_reaches_another_company(self):
        for method, path, body in (('POST', '/api/v1/mail/send', {'mailbox': 'ceo@acme.com', 'to': 'x@y.com', 'text': 'hi'}),
                                   ('POST', '/api/v1/mail/label', {'mailbox': 'ceo@acme.com', 'id': '5', 'label': 'x'}),
                                   ('GET', '/api/v1/mail/messages?mailbox=ceo@acme.com', None),
                                   ('GET', '/api/v1/mail/messages?mailbox=ceo@ACME.com', None),
                                   ('POST', '/api/v1/mail/send', {'mailbox': 'ceo@sub.acme.com', 'to': 'x@y.com', 'text': 'hi'})):
            r = api(self.s, method, path, self.other, body)
            self.assertEqual(r.status, 403, path)
            self.assertIn('other.com', r.data['error'])
            self.assertEqual(r.delegated, []); self.assertEqual(r.mail.calls, [])

    def test_shine_post_is_always_within_the_tokens_own_company(self):
        r = api(self.s, 'POST', '/api/v1/shine/post', self.other, {'channel': '#general', 'text': 'hello', 'scope': 'acme.com', 'actor': 'boss@acme.com'})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.shine, [{'op': 'post', 'scope': 'other.com', 'actor': 'chief@other.com', 'channel': 'general', 'text': 'hello'}])

    def test_send_from_own_mailbox(self):
        r = api(self.s, 'POST', '/api/v1/mail/send', self.acme, {'mailbox': 'Test@Acme.com', 'to': ['a@b.com', 'c@d.com'], 'subject': 'Hi', 'text': 'a <b>\nc'})
        self.assertEqual((r.status, r.data), (200, {'ok': True, 'id': '900'}))
        kind, token, data, sender = r.mail.calls[0]
        self.assertEqual((token, sender, data['to']), ('tok:test@acme.com', 'test@acme.com', 'a@b.com,c@d.com'))
        self.assertEqual(data['body'], 'a &lt;b&gt;<br>c')
        self.assertEqual(r.logged[0][0], 'send'); self.assertEqual(r.logged[0][3], 2)   # Reports and mail.sent webhooks, like the app
        self.assertNotIn(self.acme, repr(r.logged))

    def test_missing_permission_and_body_permission(self):
        reader = make(self.s, scopes=('mail.read',), name='reader')
        r = api(self.s, 'POST', '/api/v1/mail/send', reader, {'mailbox': 'test@acme.com', 'to': 'a@b.com', 'text': 'x'})
        self.assertEqual(r.status, 403); self.assertEqual(r.mail.calls, [])
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=test@acme.com&body=1', reader)
        self.assertEqual(r.status, 403); self.assertEqual(r.mail.calls, [])
        self.assertEqual(r.logged[0][0], 'api:mail.read'); self.assertIn('failed 403', r.logged[0][2])

    def test_messages_are_headers_only_unless_allowed(self):
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=test@acme.com&limit=5', self.acme)
        self.assertEqual(r.status, 200)
        m = r.data['messages'][0]
        self.assertEqual((m['id'], m['from'], m['subject'], m['read'], m['labels']), ('361', 'x@vendor.com', 'Invoice 7', False, ['Invoices']))
        self.assertNotIn('text', m); self.assertNotIn('secret body preview', json.dumps(r.data))
        self.assertEqual(r.mail.recip, '2')   # without it the mail server leaves out the recipients
        full = make(self.s, scopes=('mail.read', 'mail.read.body'), name='full')
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=test@acme.com&body=1', full)
        self.assertEqual(r.data['messages'][0]['text'], 'Please pay.')
        self.assertEqual(r.logged[-1][:2], ('api:mail.read', 'test@acme.com'))

    def test_label(self):
        r = api(self.s, 'POST', '/api/v1/mail/label', self.acme, {'mailbox': 'test@acme.com', 'id': '361', 'label': 'Done'})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.mail.calls, [('label', 'tok:test@acme.com', {'ids': ['361'], 'op': 'label', 'label': 'Done'})])
        r = api(self.s, 'POST', '/api/v1/mail/label', self.acme, {'mailbox': 'test@acme.com', 'id': '1 OR 2', 'label': 'Done'})
        self.assertEqual(r.status, 400)

    def test_unknown_mailbox_is_404(self):
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=ghost@acme.com', self.acme, missing=('ghost@acme.com',))
        self.assertEqual((r.status, r.data['error']), (404, 'Mailbox not found.'))

    def test_rate_limit_per_token(self):
        for _ in range(at.PER_MINUTE): api(self.s, 'GET', '/api/v1/mail/messages?mailbox=test@acme.com', self.acme)
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=test@acme.com', self.acme)
        self.assertEqual(r.status, 429); self.assertEqual(r.mail.calls, [])
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=x@other.com', self.other)
        self.assertEqual(r.status, 200)

    def test_revoked_token_is_401(self):
        self.s.action('apitoken_revoke', {'id': self.acme.split('_')[1]}, 'acme.com', 'boss@acme.com')
        r = api(self.s, 'GET', '/api/v1/mail/messages?mailbox=test@acme.com', self.acme)
        self.assertEqual((r.status, r.data), (401, {'error': 'Unauthorized'}))


class AdminWiring(unittest.TestCase):
    """Who may manage tokens, and for which domain (mirrors the webhooks wiring)."""
    def handler(self, scope, perms, actor):
        s = store(); logged = []
        h = SimpleNamespace(server=SimpleNamespace(api_tokens=s), logged=logged)
        client = SimpleNamespace(actor_perms=lambda t, a, sc: perms, call=lambda r, t=None, timeout=None: (lambda out: (ET.SubElement(out, A + 'domain', {'name': 'x'}), out)[1])(ET.Element(A + 'R')))
        h.admin_session = lambda sess: (client, 'tok', scope)
        h.log = lambda kind, a, target='', n=1: logged.append((kind, a, target))
        h.act = lambda data: z.Handler.apitoken_action(h, {'user': {'email': actor}}, data)
        return h

    def test_company_admin_only_their_own_domain_and_token_not_logged(self):
        h = self.handler('acme.com', {'roles.manage'}, 'boss@acme.com')
        out = h.act({'op': 'apitoken_add', 'domain': 'other.com', 'name': 'n8n', 'scopes': ['mail.read'], 'days': 30})
        self.assertEqual(out['domain'], 'acme.com')
        self.assertEqual(h.server.api_tokens.all.get('other.com', []), [])
        self.assertEqual(h.logged[-1][0], 'admin:apitoken_add')
        self.assertNotIn(out['token'], repr(h.logged)); self.assertNotIn(out['token'].rsplit('_', 1)[1], repr(h.logged))

    def test_needs_the_domain_settings_permission(self):
        h = self.handler('acme.com', {'mailboxes.manage'}, 'boss@acme.com')
        with self.assertRaisesRegex(z.APIError, 'does not allow'): h.act({'op': 'apitokens_get'})


if __name__ == '__main__':
    unittest.main()
