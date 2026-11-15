"""A company's own outgoing mail service: the password is sealed, the right mail takes that road, and a sent mail is filed."""
import json, smtplib, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import relay
import zimbra as z

KEY = b'k' * 32
GOOD = {'host': 'smtp.resend.com', 'port': 465, 'security': 'ssl', 'user': 'resend', 'password': 're_secret_123'}

def store(tmp, **kw): return relay.Relays(Path(tmp) / 'relays.json', key=KEY, is_public=lambda h: True, **kw)

class Sealing(unittest.TestCase):
    def test_round_trip_and_tamper(self):
        sealed = relay.seal(KEY, 'pässword 🔑')
        self.assertNotIn('pässword'.encode().hex(), sealed)
        self.assertEqual(relay.unseal(KEY, sealed), 'pässword 🔑')
        self.assertNotEqual(sealed, relay.seal(KEY, 'pässword 🔑'))                       # a fresh nonce every time
        flipped = sealed[:40] + ('0' if sealed[40] != '0' else '1') + sealed[41:]
        with self.assertRaises(relay.RelayError): relay.unseal(KEY, flipped)
        with self.assertRaises(relay.RelayError): relay.unseal(b'x' * 32, sealed)

class Settings(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.mkdtemp(); self.r = store(self.tmp)
    def test_password_never_leaves_and_is_not_on_disk(self):
        out = self.r.action('relay_set', GOOD, 'acme.in')
        self.assertEqual(out['relay']['host'], 'smtp.resend.com'); self.assertNotIn('password', out['relay'])
        self.assertNotIn('re_secret_123', (Path(self.tmp) / 'relays.json').read_text())
        self.assertEqual(self.r.config('acme.in')['password'], 're_secret_123')
        self.assertEqual(store(self.tmp).config('acme.in')['password'], 're_secret_123')     # survives a restart
    def test_saving_again_without_the_password_keeps_it(self):
        self.r.action('relay_set', GOOD, 'acme.in')
        self.r.action('relay_set', {**GOOD, 'password': '', 'departments': ['Sales']}, 'acme.in')
        self.assertEqual(self.r.config('acme.in')['password'], 're_secret_123')
        with self.assertRaises(relay.RelayError): self.r.action('relay_set', {**GOOD, 'password': '', 'host': 'smtp.other.com'}, 'acme.in')   # another server needs its own
    def test_bad_settings_are_refused(self):
        for bad in ({'host': 'localhost'}, {'port': 22}, {'security': 'none'}, {'user': ''}, {'password': ''}, {'departments': 'Sales'}):
            with self.assertRaises(relay.RelayError): self.r.action('relay_set', {**GOOD, **bad}, 'acme.in')
        private = relay.Relays(Path(self.tmp) / 'p.json', key=KEY, is_public=lambda h: False)
        with self.assertRaises(relay.RelayError): private.action('relay_set', GOOD, 'acme.in')
    def test_remove(self):
        self.r.action('relay_set', GOOD, 'acme.in')
        self.assertFalse(self.r.action('relay_remove', {}, 'acme.in')['relay']['configured'])
        self.assertIsNone(self.r.route('acme.in', '', ['x@gmail.com']))

class Routing(unittest.TestCase):
    def setUp(self): self.r = store(tempfile.mkdtemp())
    def test_only_outside_mail_of_that_company(self):
        self.r.action('relay_set', GOOD, 'acme.in')
        self.assertEqual(self.r.route('acme.in', '', ['a@acme.in', 'x@gmail.com'])['host'], 'smtp.resend.com')
        self.assertIsNone(self.r.route('acme.in', '', ['a@acme.in', 'b@ACME.in']))          # all inside: the usual way
        self.assertIsNone(self.r.route('other.in', '', ['x@gmail.com']))                    # another company has none
    def test_departments_and_off_switch(self):
        self.r.action('relay_set', {**GOOD, 'departments': ['Customer Support']}, 'acme.in')
        self.assertIsNotNone(self.r.route('acme.in', 'customer support', ['x@gmail.com']))
        self.assertIsNone(self.r.route('acme.in', 'Sales', ['x@gmail.com']))
        self.assertIsNone(self.r.route('acme.in', '', ['x@gmail.com']))
        self.r.action('relay_set', {**GOOD, 'active': False}, 'acme.in')
        self.assertIsNone(self.r.route('acme.in', 'Customer Support', ['x@gmail.com']))

class Message(unittest.TestCase):
    def test_built_mail(self):
        m = relay.build('riya@acme.in', 'Riya Sen', ['x@gmail.com'], ['c@y.com'], 'Hello\r\nBcc: evil@x.com', 'plain', '<p>rich</p>', [(b'%PDF-1', 'a.pdf', 'application/pdf')], '<1@x>', True)
        raw = m.as_string()
        self.assertEqual(m['From'], 'Riya Sen <riya@acme.in>'); self.assertEqual(m['To'], 'x@gmail.com'); self.assertEqual(m['Cc'], 'c@y.com')
        self.assertIsNone(m['Bcc']); self.assertNotIn('\nBcc:', raw)                          # no header can be smuggled in through the subject
        self.assertEqual(m['In-Reply-To'], '<1@x>'); self.assertEqual(m['Importance'], 'high')
        self.assertIn('text/html', raw); self.assertIn('filename="a.pdf"', raw); self.assertTrue(m['Message-ID'].endswith('@acme.in>'))

class Sending(unittest.TestCase):
    """send() against a stand-in for smtplib: what is said to the service, and what the admin is told when it says no."""
    def run_with(self, fake, cfg=None):
        real_ssl, real_plain = smtplib.SMTP_SSL, smtplib.SMTP
        smtplib.SMTP_SSL = smtplib.SMTP = fake
        try: relay.send({**GOOD, **(cfg or {})}, 'riya@acme.in', ['x@gmail.com', 'b@y.com'], relay.build('riya@acme.in', '', ['x@gmail.com'], [], 's', 't', None, []))
        finally: smtplib.SMTP_SSL, smtplib.SMTP = real_ssl, real_plain
    def test_logs_in_and_sends_to_everyone_including_bcc(self):
        seen = {}
        class Fake:
            def __init__(self, host, port, **kw): seen['at'] = (host, port)
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def starttls(self, **kw): seen['tls'] = True
            def login(self, u, p): seen['login'] = (u, p)
            def send_message(self, msg, from_addr, to_addrs): seen['env'] = (from_addr, to_addrs); return {}
        self.run_with(Fake)
        self.assertEqual(seen, {'at': ('smtp.resend.com', 465), 'login': ('resend', 're_secret_123'), 'env': ('riya@acme.in', ['x@gmail.com', 'b@y.com'])})
        seen.clear(); self.run_with(Fake, {'port': 587, 'security': 'starttls'}); self.assertTrue(seen['tls'])   # never the password before TLS
    def test_refusals_are_explained(self):
        def failing(error):
            class Fake:
                def __init__(self, *a, **kw): pass
                def __enter__(self): return self
                def __exit__(self, *a): pass
                def login(self, u, p): raise error
            return Fake
        for error, words in ((smtplib.SMTPAuthenticationError(535, b'bad'), 'user name and password'), (smtplib.SMTPSenderRefused(554, b'Email address is not verified', 'riya@acme.in'), 'verify the domain'), (OSError('timed out'), 'Could not reach')):
            with self.assertRaises(relay.RelayError) as raised: self.run_with(failing(error))
            self.assertIn(words, str(raised.exception))

class TestButton(unittest.TestCase):
    def test_sends_to_the_admin_and_records_the_result(self):
        got = []; r = store(tempfile.mkdtemp(), deliver=lambda cfg, sender, to, msg: got.append((cfg['password'], sender, to, msg['Subject'])))
        r.action('relay_set', GOOD, 'acme.in')
        out = r.action('relay_test', {}, 'acme.in', 'admin@acme.in')
        self.assertTrue(out['sent']); self.assertTrue(out['relay']['last']['ok']); self.assertEqual(got[0][:3], ('re_secret_123', 'admin@acme.in', ['admin@acme.in']))
        with self.assertRaises(relay.RelayError): r.action('relay_test', {}, 'acme.in', 'someone@else.in')
    def test_a_refusal_is_recorded(self):
        def no(*a): raise relay.RelayError('Your mail service did not accept the user name and password.')
        r = store(tempfile.mkdtemp(), deliver=no); r.action('relay_set', GOOD, 'acme.in')
        with self.assertRaises(relay.RelayError): r.action('relay_test', {}, 'acme.in', 'admin@acme.in')
        self.assertFalse(r.action('relay_get', {}, 'acme.in')['relay']['last']['ok'])

class SendThroughIt(unittest.TestCase):
    """The web send: out through the company's service, a copy in Sent with Bcc, the draft removed; a refusal sends nothing."""
    def handler(self, deliver):
        calls = []
        class Zimbra:
            app_url = 'https://mail.dejoiy.com'
            def file_sent(self, token, raw): calls.append(('sent', raw)); return '900'
            def action(self, token, data): calls.append(('action', data)); return {'ok': True}
            def download(self, token, mid, part): return b'forwarded-file'
        h = z.Handler.__new__(z.Handler)
        h.server = type('S', (), {'zimbra': Zimbra(), 'relays': store(tempfile.mkdtemp())})()
        h.server.relays.action('relay_set', GOOD, 'acme.in'); h.domain = lambda s: 'acme.in'
        self.real = relay.send; relay.send = deliver; self.addCleanup(lambda: setattr(relay, 'send', self.real))
        return h, calls
    SESSION = {'token': 't', 'user': {'email': 'riya@acme.in', 'name': 'Riya Sen'}}
    DATA = {'to': 'x@gmail.com', 'cc': '', 'bcc': 'boss@acme.in', 'subject': 'Quote', 'body': '<p>Hi</p>', 'label': 'Work', 'id': '77',
            'attachments': [{'name': 'q.pdf', 'type': 'application/pdf', 'data': 'JVBERi0x'}, {'mid': '5', 'part': '2', 'name': 'old.txt'}]}
    def test_goes_out_and_is_filed(self):
        wire = []
        h, calls = self.handler(lambda cfg, sender, to, msg: wire.append((cfg['host'], sender, to, msg.as_string())))
        cfg = h.relay_route(self.SESSION, self.DATA); self.assertEqual(cfg['host'], 'smtp.resend.com')
        out = h.relay_send(self.SESSION, self.DATA, cfg)
        self.assertEqual(out, {'id': '900', 'accepted': True, 'draftRemoved': True, 'via': 'smtp.resend.com'})
        host, sender, to, raw = wire[0]
        self.assertEqual((sender, to), ('riya@acme.in', ['x@gmail.com', 'boss@acme.in'])); self.assertNotIn('boss@acme.in', raw)   # Bcc is not on the wire
        self.assertIn('filename="q.pdf"', raw); self.assertIn('filename="old.txt"', raw); self.assertIn('Dejoiy Mail', raw)
        self.assertIn('Bcc: boss@acme.in', calls[0][1])                                                                         # but your Sent copy shows it
        self.assertEqual([c[1] for c in calls[1:]], [{'ids': ['900'], 'op': 'label', 'label': 'Work'}, {'ids': ['77'], 'op': 'delete'}])
        self.assertTrue(h.server.relays.action('relay_get', {}, 'acme.in')['relay']['last']['ok'])
    def test_a_refusal_sends_nothing_and_files_nothing(self):
        def no(*a): raise relay.RelayError('Your mail service did not accept the user name and password.')
        h, calls = self.handler(no)
        with self.assertRaises(z.APIError) as raised: h.relay_send(self.SESSION, self.DATA, h.relay_route(self.SESSION, self.DATA))
        self.assertEqual(raised.exception.code, 'relay'); self.assertEqual(calls, [])
    def test_inside_mail_takes_the_usual_way(self):
        h, _ = self.handler(lambda *a: None)
        self.assertIsNone(h.relay_route(self.SESSION, {'to': 'b@acme.in', 'cc': '', 'bcc': ''}))

if __name__ == '__main__': unittest.main()


class SwissMail(unittest.TestCase):
    """The Swiss Mail add-on (set up by Dejoiy) and a Swiss Mail key a company pastes itself."""
    KEY_ = 'djy_live_' + 'A' * 28
    def setUp(self): self.tmp = tempfile.mkdtemp(); self.r = store(self.tmp)

    def test_pasted_key_is_sealed_and_mail_goes_to_the_raw_api(self):
        with self.assertRaises(relay.RelayError): self.r.action('relay_set', {'kind': 'swiss', 'key': 'nope'}, 'acme.in')
        out = self.r.action('relay_set', {'kind': 'swiss', 'key': self.KEY_}, 'acme.in')
        self.assertEqual((out['relay']['kind'], out['relay']['keyStart']), ('swiss', self.KEY_[:12]))
        self.assertNotIn(self.KEY_, (Path(self.tmp) / 'relays.json').read_text())
        cfg = self.r.route('acme.in', '', ['x@gmail.com'])
        seen = {}
        class Resp:
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def read(s): return b'{"id":"em_1"}'
        def opener(request, timeout):
            seen.update(url=request.full_url, auth=request.headers['Authorization'], body=json.loads(request.data)); return Resp()
        msg = relay.build('boss@acme.in', 'Boss', ['x@gmail.com'], [], 'Hi', 'Hello', None, [(b'pdf', 'a.pdf', 'application/pdf')])
        relay.send_swiss(cfg, 'boss@acme.in', ['x@gmail.com', 'y@gmail.com'], msg, opener=opener)
        self.assertEqual(seen['url'], relay.SWISS_URL + '/v1/emails/raw')
        self.assertEqual(seen['auth'], 'Bearer ' + self.KEY_)
        self.assertEqual(seen['body']['rcpt_to'], ['x@gmail.com', 'y@gmail.com'])
        import base64
        self.assertIn(b'filename="a.pdf"', base64.b64decode(seen['body']['data']))

    def test_swiss_refusals_are_readable(self):
        import io, urllib.error
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, 'x', {}, io.BytesIO(b'{"error":{"message":"This month\'s 10,000 mails are used up."}}'))
        with self.assertRaisesRegex(relay.RelayError, '10,000 mails'): relay.swiss_call('POST', '/v1/emails/raw', 'k', {}, opener=opener)
        def nokey(request, timeout): raise urllib.error.HTTPError(request.full_url, 401, 'x', {}, io.BytesIO(b'{}'))
        with self.assertRaisesRegex(relay.RelayError, 'did not accept the key'): relay.swiss_call('GET', '/x', 'k', opener=nokey)

    def test_addon_is_used_only_while_paid(self):
        paid = {'acme.in': 0}
        self.r.addon_until = lambda d: paid.get(d, 0)
        self.assertTrue(self.r.set_addon('acme.in', self.KEY_))
        self.assertIsNone(self.r.route('acme.in', '', ['x@gmail.com']))           # not paid: the usual way
        import time
        paid['acme.in'] = time.time() + 86400
        self.assertIsNone(self.r.route('acme.in', '', ['x@gmail.com']))           # paid, but Swiss Mail hasn't verified the domain
        self.r.set_addon('acme.in', verified=True)
        self.assertEqual(self.r.route('acme.in', '', ['x@gmail.com'])['password'], self.KEY_)
        self.assertFalse(self.r.set_addon('other.in'))                              # nothing to update without a key
        self.assertTrue(self.r.set_addon('acme.in', suspended=True))
        self.assertTrue(self.r.all['acme.in']['suspended'])


class SesList(unittest.TestCase):
    def test_dejoiy_domains_and_promoted_ones(self):
        tmp = Path(tempfile.mkdtemp())
        class S: reserved_domains = {'dejoiy.com'}; ses_file = str(tmp / 'ses.txt'); promoted_file = tmp / 'p.json'
        z.write_ses_list(S)
        self.assertEqual((tmp / 'ses.txt').read_text(), '*.dejoiy.com\n')
        z.write_ses_list(S, {'kaali.in'})
        self.assertEqual((tmp / 'ses.txt').read_text(), '*.dejoiy.com\nkaali.in\n')
        self.assertTrue(z.uses_ses(S, 'corp.dejoiy.com')); self.assertTrue(z.uses_ses(S, 'kaali.in'))
        self.assertFalse(z.uses_ses(S, 'notdejoiy.com'))
