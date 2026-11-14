"""Undelivered mail: log parsing, the admin page (company admins see only their own domain) and
the web send path that must never let a refused message vanish (kept in Drafts, logged, explained)."""
import json, os, sys, tempfile, threading, time, unittest, urllib.request, urllib.error
from unittest.mock import Mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import undelivered as u
import zimbra as z
import zconsole as c

T = '2026-11-14T09:%s.000000+01:00 mail '
MAIL = [
    # outbound virus, amavis D_BOUNCE: sender told (reason joined from the amavis line by its id)
    T % '54:32' + 'postfix/qmgr[1]: 15379200F00: from=<test@corp.dejoiy.com>, size=900, nrcpt=1 (queue active)',
    T % '54:32' + 'postfix/smtp[2]: 15379200F00: to=<partners.dejoiy@gmail.com>, relay=127.0.0.1[127.0.0.1]:10026, delay=0.4, delays=0/0/0/0.3, dsn=2.5.0, status=sent (250 2.5.0 Ok, id=4097265-01, BOUNCE)',
    # outbound encrypted PDF, old D_DISCARD: nobody told
    T % '06:00' + 'postfix/qmgr[1]: 1C9E9200F0C: from=<deepak@corp.dejoiy.com>, size=900, nrcpt=1 (queue active)',
    T % '06:00' + 'postfix/smtp[2]: 1C9E9200F0C: to=<someone@gmail.com>, relay=127.0.0.1[127.0.0.1]:10026, delay=2, delays=0/0/0/1, dsn=2.7.0, status=sent (250 2.7.0 Ok, discarded, id=3763836-01 - INFECTED: Heuristics.Encrypted.PDF)',
    # remote 550, postfix tells the sender
    T % '59:59' + 'postfix/qmgr[1]: 7A4D2200F16: from=<test@corp.dejoiy.com>, size=500, nrcpt=1 (queue active)',
    T % '59:59' + 'postfix/smtp[2]: 7A4D2200F16: to=<xyz@dejoiy.com>, relay=mx.zoho.in[169.148.149.118]:25, delay=2, delays=0/0/1/1, dsn=5.1.1, status=bounced (host mx.zoho.in[169.148.149.118] said: 550 5.1.1 User does not exist - <xyz@dejoiy.com> (in reply to RCPT TO command))',
    T % '59:59' + 'postfix/bounce[3]: 7A4D2200F16: sender non-delivery notification: EE3FC200F17',
    # deferred once, then delivered: not undelivered
    T % '57:54' + 'postfix/qmgr[1]: 0E059200DD4: from=<test@corp.dejoiy.com>, size=556, nrcpt=1 (queue active)',
    T % '57:54' + 'postfix/smtp[2]: 0E059200DD4: to=<partners.dejoiy@gmail.com>, relay=none, delay=0.1, delays=0/0/0/0, dsn=4.4.1, status=deferred (connect to 127.0.0.1[127.0.0.1]:10026: Connection refused)',
    T % '58:36' + 'postfix/smtp[2]: 0E059200DD4: to=<partners.dejoiy@gmail.com>, relay=127.0.0.1[127.0.0.1]:10026, delay=43, delays=42/0/0/0.5, dsn=2.0.0, status=sent (250 2.0.0 from MTA(smtp:[127.0.0.1]:10030): 250 2.0.0 Ok: queued as 13355200DD4)',
    # still deferred, delay notice sent
    T % '30:00' + 'postfix/qmgr[1]: AAAAAA00001: from=<ravi@other.in>, size=556, nrcpt=1 (queue active)',
    T % '30:00' + 'postfix/smtp[2]: AAAAAA00001: to=<x@slow.example>, relay=none, delay=9000, delays=0/0/0/0, dsn=4.4.1, status=deferred (connect to mx.slow.example[1.2.3.4]:25: Connection timed out)',
    T % '30:01' + 'postfix/bounce[3]: AAAAAA00001: sender delay notification: BBBBBB00001',
    # size limit refused at SMTP time from our own server
    T % '59:57' + 'postfix/smtpd[4]: NOQUEUE: reject: MAIL from mail.dejoiy.com[173.249.23.93]: 552 5.3.4 Message size exceeds fixed limit; from=<test@corp.dejoiy.com> proto=ESMTP helo=<mail.dejoiy.com>',
    # an outside bot rejected: not ours, not listed
    T % '59:58' + 'postfix/smtpd[4]: NOQUEUE: reject: RCPT from unknown[85.1.1.1]: 554 5.7.1 Relay access denied; from=<spam@bad.example> to=<a@b.example> proto=ESMTP helo=<x>',
    # SES returns a remote bounce as a new message from <>
    T % '00:10' + 'postfix/smtpd[5]: 08BFE200F16: client=c180-240.smtp-out.ap-south-1.amazonses.com[76.223.180.240]',
    T % '00:10' + 'postfix/qmgr[1]: 08BFE200F16: from=<>, size=3000, nrcpt=1 (queue active)',
    T % '00:11' + 'postfix/smtp[2]: 08BFE200F16: to=<test@corp.dejoiy.com>, relay=127.0.0.1[127.0.0.1]:10024, delay=1, delays=0/0/0/1, dsn=2.0.0, status=sent (250 2.0.0 from MTA(smtp:[127.0.0.1]:10025): 250 2.0.0 Ok: queued as 1)',
    # a bounce of a bounce: nobody to tell
    T % '30:30' + 'postfix/qmgr[1]: 08EEC2008F8: from=<>, size=7341, nrcpt=1 (queue active)',
    T % '30:30' + 'postfix/error[6]: 08EEC2008F8: to=<admin@mail.dejoiy.com>, relay=none, delay=0.1, delays=0/0/0/0, dsn=5.0.0, status=bounced (mail.dejoiy.com)',
]
AMAVIS = ['Nov 14 09:54:32 mail amavis[4097265]: (4097265-01) Blocked INFECTED (Eicar-Test-Signature) {BouncedOutbound,Quarantined}, ORIGINATING/MYNETS LOCAL [173.249.23.93]:34248 [173.249.23.93] <test@corp.dejoiy.com> -> <partners.dejoiy@gmail.com>, quarantine: virus-quarantine@corp.dejoiy.com, Queue-ID: 15379200F00']


def by_qid(rows):
    return {r['qid']: r for r in rows if r['qid']}


class Parse(unittest.TestCase):
    def setUp(self):
        self.rows = u.parse(MAIL, AMAVIS, now=time.mktime((2026, 11, 14, 12, 0, 0, 0, 0, -1)))
        self.q = by_qid(self.rows)

    def test_amavis_bounce_tells_sender_with_plain_reason(self):
        r = self.q['15379200F00']
        self.assertEqual((r['outcome'], r['notified'], r['direction'], r['from']), ('stopped', 'sender', 'outbound', 'test@corp.dejoiy.com'))
        self.assertEqual(r['reason'], 'Attachment mein virus mila (Eicar-Test-Signature)')

    def test_silent_discard_is_flagged_as_nobody_told(self):
        r = self.q['1C9E9200F0C']
        self.assertEqual((r['outcome'], r['action'], r['notified']), ('stopped', 'discarded', 'no'))
        self.assertIn('Heuristics.Encrypted.PDF', r['reason'])

    def test_remote_bounce_and_notice(self):
        r = self.q['7A4D2200F16']
        self.assertEqual((r['outcome'], r['notified'], r['to']), ('bounced', 'sender', 'xyz@dejoiy.com'))
        self.assertTrue(r['reason'].startswith('Ye mailbox maujood nahi hai'))

    def test_deferred_then_delivered_is_not_listed_but_still_waiting_is(self):
        self.assertNotIn('0E059200DD4', self.q)
        r = self.q['AAAAAA00001']
        self.assertEqual((r['outcome'], r['notified']), ('waiting', 'sender (delay notice)'))

    def test_smtp_reject_only_from_our_server(self):
        rejects = [r for r in self.rows if r['outcome'] == 'rejected']
        self.assertEqual(len(rejects), 1)
        self.assertEqual((rejects[0]['from'], rejects[0]['notified']), ('test@corp.dejoiy.com', 'sender (at send time)'))
        self.assertTrue(rejects[0]['reason'].startswith('Mail size limit se badi thi'))

    def test_ses_bounce_and_bounce_of_bounce(self):
        ses = [r for r in self.rows if 'Amazon SES' in r['reason']]
        self.assertEqual(len(ses), 1); self.assertEqual(ses[0]['from'], 'test@corp.dejoiy.com')
        r = self.q['08EEC2008F8']
        self.assertEqual((r['from'], r['notified'], r['direction']), ('(system)', 'no', 'system'))
        self.assertEqual(r['reason'], 'Is server pe ye mailbox maujood nahi hai: mail.dejoiy.com')


class IndexAndScope(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.path = os.path.join(self.dir.name, 'u.db')
        now = time.mktime((2026, 11, 14, 12, 0, 0, 0, 0, -1))
        u.write_index(u.parse(MAIL, AMAVIS, now=now), self.path, now=now); self.now = now

    def tearDown(self): self.dir.cleanup()

    def test_index_is_private_and_readable(self):
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o640)
        out = u.Undelivered(self.path).query(now=self.now)
        self.assertTrue(out['available']); self.assertEqual(len(out['rows']), 7)

    def test_company_admin_only_sees_own_domain(self):
        rows = u.Undelivered(self.path).query('other.in', now=self.now)['rows']
        self.assertEqual([r['from'] for r in rows], ['ravi@other.in'])
        rows = u.Undelivered(self.path).query('corp.dejoiy.com', now=self.now)['rows']
        self.assertTrue(rows and all('corp.dejoiy.com' in (r['from'] + r['to']) for r in rows))
        self.assertNotIn('ravi@other.in', [r['from'] for r in rows])

    def test_missing_index_is_reported_not_faked(self):
        out = u.Undelivered(os.path.join(self.dir.name, 'none.db')).query()
        self.assertEqual(out, {'rows': [], 'indexedAt': None, 'available': False})


class ConsolePage(unittest.TestCase):
    def make(self, scope, perms=None):
        con = c.Console(Mock(), 't', 'boss@' + (scope or 'dejoiy.com'), scope, perms, z.APIError)
        log_rows = [{'ts': 100.0, 'qid': 'Q1', 'from': 'a@kaali.in', 'to': 'x@gmail.com', 'outcome': 'bounced', 'action': 'returned', 'direction': 'outbound', 'reason': 'r', 'notified': 'sender'},
                    {'ts': 90.0, 'qid': 'Q2', 'from': 'b@other.in', 'to': 'y@gmail.com', 'outcome': 'stopped', 'action': 'discarded', 'direction': 'outbound', 'reason': 'r', 'notified': 'no'},
                    {'ts': 80.0, 'qid': 'Q3', 'from': 'z@yahoo.com', 'to': 'c@kaali.in', 'outcome': 'stopped', 'action': 'discarded', 'direction': 'inbound', 'reason': 'r', 'notified': 'recipient'}]
        src = Mock(); src.query.side_effect = lambda scope: {'rows': [dict(r) for r in log_rows if not scope or scope in r['from'] + r['to']], 'indexedAt': 5, 'available': True}
        con.undelivered = src
        failed = [{'ts': 110.0, 'from': 'a@kaali.in', 'to': 'q@gmail.com', 'code': 'mail.MESSAGE_TOO_BIG'},
                  {'ts': 95.0, 'from': 'b@other.in', 'to': 'p@gmail.com', 'code': 'transport'}]
        con.failed_sends = lambda scope: [f for f in failed if not scope or f['from'].endswith('@' + scope)]
        return con, src

    def test_company_admin_sees_only_its_domain_including_failed_web_sends(self):
        con, src = self.make('kaali.in')
        out = con.run({'op': 'z_undelivered'})
        src.query.assert_called_with('kaali.in')
        self.assertEqual([r['qid'] or r['outcome'] for r in out['rows']], ['refused', 'Q1', 'Q3'])
        self.assertTrue(all('kaali.in' in r['from'] + r['to'] for r in out['rows']))
        refused = out['rows'][0]
        self.assertEqual(refused['action'], 'kept in Drafts'); self.assertIn('Mail size limit se badi thi', refused['reason'])
        self.assertEqual(out['notToldCount'], 0)
        self.assertEqual(refused['at'], 110000)

    def test_scope_filter_holds_even_if_the_source_returns_too_much(self):
        con, src = self.make('kaali.in'); con.failed_sends = lambda scope: []
        src.query.side_effect = lambda scope: {'rows': [{'ts': 1.0, 'qid': 'X', 'from': 'b@other.in', 'to': 'y@gmail.com', 'outcome': 'bounced', 'action': 'r', 'direction': 'outbound', 'reason': 'r', 'notified': 'no'}], 'indexedAt': 1, 'available': True}
        self.assertEqual(con.run({'op': 'z_undelivered'})['rows'], [])

    def test_platform_team_sees_everything(self):
        con, _ = self.make(None)
        out = con.run({'op': 'z_undelivered'})
        self.assertEqual(len(out['rows']), 5); self.assertEqual(out['notToldCount'], 1)

    def test_role_without_mailbox_permission_is_refused(self):
        con, src = self.make('kaali.in', perms={'teams.manage'})
        with self.assertRaisesRegex(z.APIError, 'does not allow'): con.run({'op': 'z_undelivered'})
        src.query.assert_not_called()

    def test_is_a_lookup_so_not_audited_as_a_change(self):
        self.assertIn('z_undelivered', c.LOOKUPS)


class Limits(unittest.TestCase):
    def test_attachment_limit_follows_the_mail_server(self):
        l = z.attachment_limits('10240000', '10485760')
        self.assertEqual((l['messageBytes'], l['uploadBytes']), (10240000, 10485760))
        self.assertEqual(l['attachmentBytes'], int((10240000 - 256 * 1024) / 1.37))
        self.assertLess(l['attachmentBytes'], 7.5 * 1024 * 1024)
        self.assertEqual(z.attachment_limits(None, None)['attachmentBytes'], z.MAX_ATTACHMENT_BYTES)
        self.assertEqual(z.attachment_limits('100000000', '2000000')['attachmentBytes'], 2000000)

    def test_upload_rejected_as_too_big_says_so(self):
        zc = z.Zimbra.__new__(z.Zimbra); zc.origin = 'https://mail.example'
        resp = Mock(); resp.read.return_value = b"413,'null'"; resp.__enter__ = Mock(return_value=resp); resp.__exit__ = Mock(return_value=False)
        zc.opener = Mock(); zc.opener.open.return_value = resp
        with self.assertRaises(z.APIError) as e: zc.upload('tok', b'x', 'statement.pdf', 'application/pdf')
        self.assertEqual((e.exception.status, e.exception.code), (413, 'upload_too_big'))
        self.assertIn('statement.pdf', str(e.exception))


class SendFailure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = z.ThreadingHTTPServer(('127.0.0.1', 0), z.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port); cls.server.app_origin = cls.url; cls.server.attempts = {}
        cls.server.zimbra = Mock(); cls.server.zimbra.login.return_value = ('private-token', 3600)
        cls.server.audit = z.AuditLog()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        self.z = self.server.zimbra; self.z.reset_mock(); self.z.login.return_value = ('private-token', 3600)
        self.z.capabilities.return_value = {'isAdmin': False, 'canManageRoles': False}; self.z.account_id.return_value = 'acc-1'
        self.z.write_message.side_effect = None; self.z.sent_copy.side_effect = None
        self.server.attempts = {}

    def request(self, path, data=None, cookie=None, csrf=None):
        headers = {}
        if cookie: headers['Cookie'] = cookie
        if csrf: headers['X-CSRF-Token'] = csrf
        if data is not None: headers.update({'Content-Type': 'application/json', 'Origin': self.url})
        req = urllib.request.Request(self.url + path, None if data is None else json.dumps(data).encode(), headers)
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read().decode())

    def login(self, email='ravi@kaali.in'):
        req = urllib.request.Request(self.url + '/api/login', json.dumps({'email': email, 'password': 'x'}).encode(), {'Content-Type': 'application/json', 'Origin': self.url})
        with urllib.request.urlopen(req) as r:
            return r.headers['Set-Cookie'].split(';')[0], json.loads(r.read().decode())['csrf']

    def failures(self):
        return self.server.audit.failures(None, now=time.time() + 1)

    def test_refused_send_is_kept_in_drafts_logged_and_explained(self):
        cookie, csrf = self.login()
        calls = []
        def write(token, data, draft=False, sender=''):
            calls.append(draft)
            if not draft: raise z.APIError('The message is larger than the mail server allows.', 502, 'mail.MESSAGE_TOO_BIG')
            return {'id': '77', 'accepted': False}
        self.z.write_message.side_effect = write
        status, body = self.request('/api/send', {'to': 'x@gmail.com', 'subject': 'Statement', 'id': '55'}, cookie, csrf)
        self.assertEqual(status, 502)
        self.assertEqual(calls, [False, True])  # tried to send, then saved the draft
        self.assertEqual(self.z.write_message.call_args_list[1][0][1]['id'], '55')  # the open draft is updated, not duplicated
        self.assertEqual((body['draftId'], body['notSent']), ('77', True))
        self.assertIn('saved in Drafts and was not sent', body['error'])
        got = self.failures()
        self.assertEqual(got[0]['code'], 'mail.MESSAGE_TOO_BIG'); self.assertEqual(got[0]['to'], 'x@gmail.com'); self.assertEqual(got[0]['from'], 'ravi@kaali.in')

    def test_too_big_for_a_draft_keeps_the_text_without_the_new_files(self):
        cookie, csrf = self.login()
        seen = []
        def write(token, data, draft=False, sender=''):
            seen.append((draft, [a.get('name') for a in data.get('attachments', [])]))
            if not draft or any(a.get('data') for a in data.get('attachments', [])):
                raise z.APIError('The message is larger than the mail server allows.', 502, 'mail.MESSAGE_TOO_BIG')
            return {'id': '79'}
        self.z.write_message.side_effect = write
        files = [{'name': 'big.pdf', 'data': 'QUJD', 'type': 'application/pdf'}, {'name': 'old.pdf', 'mid': '5', 'part': '2'}]
        status, body = self.request('/api/send', {'to': 'x@gmail.com', 'subject': 'S', 'attachments': files}, cookie, csrf)
        self.assertEqual((status, body['draftId']), (502, '79'))
        self.assertEqual(seen, [(False, ['big.pdf', 'old.pdf']), (True, ['big.pdf', 'old.pdf']), (True, ['old.pdf'])])
        self.assertIn('attach big.pdf again', body['error'])

    def test_timeout_that_actually_went_out_is_reported_as_sent_not_resent(self):
        cookie, csrf = self.login()
        self.z.write_message.side_effect = z.APIError('Mail server is unavailable. Try again later.', 502, 'transport')
        self.z.sent_copy.return_value = '99'
        status, body = self.request('/api/send', {'to': 'x@gmail.com', 'subject': 'Hi'}, cookie, csrf)
        self.assertEqual((status, body['id'], body['confirmedLate']), (200, '99', True))
        self.assertEqual(self.z.write_message.call_count, 1)  # no draft, no second send

    def test_timeout_not_in_sent_is_kept_in_drafts(self):
        cookie, csrf = self.login()
        def write(token, data, draft=False, sender=''):
            if not draft: raise z.APIError('Mail server is unavailable. Try again later.', 502, 'transport')
            return {'id': '78'}
        self.z.write_message.side_effect = write; self.z.sent_copy.return_value = None
        status, body = self.request('/api/send', {'to': 'x@gmail.com', 'subject': 'Hi'}, cookie, csrf)
        self.assertEqual((status, body['draftId']), (502, '78'))
        self.assertIn('could not confirm', body['error'])

    def test_input_mistakes_are_not_counted_as_undelivered(self):
        cookie, csrf = self.login()
        self.z.write_message.side_effect = z.APIError('Add a recipient')
        before = len(self.failures())
        status, body = self.request('/api/send', {'to': '', 'subject': 'Hi'}, cookie, csrf)
        self.assertEqual((status, body), (400, {'error': 'Add a recipient'}))
        self.assertEqual(len(self.failures()), before); self.assertEqual(self.z.write_message.call_count, 1)

    def test_draft_save_failing_too_still_tells_the_person(self):
        cookie, csrf = self.login()
        self.z.write_message.side_effect = z.APIError('The mail server could not send this message.', 502, 'mail.SEND_FAILURE')
        status, body = self.request('/api/send', {'to': 'x@gmail.com'}, cookie, csrf)
        self.assertEqual(status, 502); self.assertIsNone(body['draftId'])
        self.assertIn('Copy your text', body['error'])


class FaultMessages(unittest.TestCase):
    def test_send_fault_codes_have_plain_messages(self):
        zc = z.Zimbra.__new__(z.Zimbra); zc.url = 'https://m/service/soap/'
        for code, words in (('mail.SEND_PARTIAL_ADDRESS_FAILURE', 'recipient addresses were rejected'), ('mail.TRY_AGAIN', 'busy'),
                            ('mail.MESSAGE_TOO_BIG', 'larger than the mail server allows')):
            body = (f'<soap:Envelope xmlns:soap="{z.SOAP}"><soap:Body><soap:Fault><soap:Detail><Error xmlns="urn:zimbra"><Code>{code}</Code></Error></soap:Detail></soap:Fault></soap:Body></soap:Envelope>').encode()
            err = urllib.error.HTTPError('u', 500, 'x', {}, None); err.read = lambda n=0, b=body: b
            zc.opener = Mock(); zc.opener.open.side_effect = err
            with self.assertRaises(z.APIError) as e: zc.call(z.node(z.MAIL, 'SendMsgRequest'), 't')
            self.assertIn(words, str(e.exception)); self.assertEqual(e.exception.code, code)

    def test_connection_reset_is_a_transport_failure(self):
        zc = z.Zimbra.__new__(z.Zimbra); zc.url = 'https://m/service/soap/'
        zc.opener = Mock(); zc.opener.open.side_effect = ConnectionResetError()
        with self.assertRaises(z.APIError) as e: zc.call(z.node(z.MAIL, 'SendMsgRequest'), 't')
        self.assertEqual(e.exception.code, 'transport')


if __name__ == '__main__':
    unittest.main()
