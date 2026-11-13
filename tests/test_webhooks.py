import json, sys, tempfile, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import webhooks as w


class Rig:
    """A Webhooks store with no network: records every post and answers what the test says."""
    def __init__(self, answers=(200,), public=True):
        self.dir = tempfile.TemporaryDirectory()
        self.sent, self.answers, self.waits = [], list(answers), []
        def post(url, headers, body):
            self.sent.append((url, headers, body))
            return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        self.hooks = w.Webhooks(Path(self.dir.name) / 'webhooks.json', is_public=lambda host: public, post=post, sleep=self.waits.append)
    def add(self, events=('mail.sent',), url='https://hooks.acme.com/in', domain='acme.com'):
        return self.hooks.action('webhook_add', {'url': url, 'events': list(events)}, domain)
    def drain(self):
        while not self.hooks.jobs.empty(): self.hooks.work_one()


class Rules(unittest.TestCase):
    def test_only_public_https_addresses_are_accepted(self):
        for bad in ('http://hooks.acme.com/in', 'https://user:pw@hooks.acme.com/in', 'https://hooks.acme.com:8443/in', 'ftp://x', '', 'https://'):
            with self.assertRaises(w.WebhookError, msg=bad): w.clean_url(bad, lambda host: True)
        with self.assertRaises(w.WebhookError): w.clean_url('https://intranet.local/in', lambda host: False)
        self.assertEqual(w.clean_url('https://hooks.acme.com', lambda host: True), 'https://hooks.acme.com/')

    def test_private_and_loopback_hosts_are_not_public(self):
        for host in ('127.0.0.1', '10.0.0.5', '169.254.169.254', '::1', 'no-such-host.invalid'):
            self.assertFalse(w.public_host(host), host)

    def test_event_names(self):
        self.assertEqual([w.event_for(k) for k in ('send', 'signin', 'signin_failed', 'admin_signin', 'admin:create_account', 'unknown')],
                         ['mail.sent', 'signin.ok', 'signin.failed', 'admin.signin', 'admin.action', ''])


class Admin(unittest.TestCase):
    def test_secret_is_shown_once_and_never_listed(self):
        rig = Rig(); made = rig.add()
        self.assertTrue(made['secret'].startswith('whsec_'))
        listed = rig.hooks.action('webhooks_get', {}, 'acme.com')
        self.assertNotIn('secret', json.dumps(listed))
        self.assertEqual(listed['webhooks'][0]['url'], 'https://hooks.acme.com/in')

    def test_limits_and_bad_input(self):
        rig = Rig()
        with self.assertRaises(w.WebhookError): rig.add(events=['made.up'])
        with self.assertRaises(w.WebhookError): rig.hooks.action('webhooks_get', {}, '../etc')
        rig.add()
        with self.assertRaises(w.WebhookError): rig.add()                      # same address twice
        for i in range(w.MAX_PER_DOMAIN - 1): rig.add(url=f'https://hooks.acme.com/{i}')
        with self.assertRaises(w.WebhookError): rig.add(url='https://hooks.acme.com/extra')

    def test_one_company_cannot_touch_anothers_webhook(self):
        rig = Rig(); made = rig.add()
        with self.assertRaises(w.WebhookError): rig.hooks.action('webhook_remove', {'id': made['id']}, 'other.com')
        self.assertEqual(len(rig.hooks.action('webhooks_get', {}, 'acme.com')['webhooks']), 1)

    def test_survives_a_restart_and_file_is_private(self):
        rig = Rig(); rig.add()
        again = w.Webhooks(rig.hooks.path)
        self.assertEqual(len(again.listing('acme.com')['webhooks']), 1)
        self.assertEqual(rig.hooks.path.stat().st_mode & 0o777, 0o600)


class Sending(unittest.TestCase):
    def test_note_is_signed_and_carries_no_mail_content(self):
        rig = Rig(); made = rig.add()
        self.assertEqual(rig.hooks.emit('send', 'asha@acme.com', n=3), 1); rig.drain()
        url, headers, body = rig.sent[0]
        note = json.loads(body)
        self.assertEqual((note['type'], note['domain'], note['actor'], note['count']), ('mail.sent', 'acme.com', 'asha@acme.com', 3))
        self.assertEqual(set(note), {'id', 'time', 'type', 'domain', 'actor', 'target', 'count'})
        self.assertTrue(w.verify(made['secret'], headers['X-Dejoiy-Signature'], body))
        self.assertFalse(w.verify(made['secret'], headers['X-Dejoiy-Signature'], body + b' '))
        self.assertFalse(w.verify('whsec_wrong', headers['X-Dejoiy-Signature'], body))
        self.assertFalse(w.verify(made['secret'], headers['X-Dejoiy-Signature'], body, now=time.time() + 3600))

    def test_only_the_right_company_and_chosen_events(self):
        rig = Rig(); rig.add(events=['mail.sent'])
        self.assertEqual(rig.hooks.emit('send', 'x@other.com'), 0)
        self.assertEqual(rig.hooks.emit('signin', 'asha@acme.com'), 0)
        self.assertEqual(rig.hooks.emit('made_up', 'asha@acme.com'), 0)
        rig.drain(); self.assertEqual(rig.sent, [])

    def test_retries_server_errors_but_not_refusals(self):
        rig = Rig(answers=[500, 0, 200]); rig.add(); rig.hooks.emit('send', 'a@acme.com'); rig.drain()
        self.assertEqual((len(rig.sent), rig.waits), (3, list(w.RETRY_WAITS)))
        self.assertTrue(rig.hooks.listing('acme.com')['webhooks'][0]['last']['ok'])
        rig = Rig(answers=[404]); rig.add(); rig.hooks.emit('send', 'a@acme.com'); rig.drain()
        self.assertEqual(len(rig.sent), 1)
        self.assertEqual(rig.hooks.listing('acme.com')['webhooks'][0]['failures'], 1)

    def test_switches_itself_off_after_many_failures_and_back_on_by_hand(self):
        rig = Rig(answers=[410]); made = rig.add()
        for _ in range(w.PAUSE_AFTER): rig.hooks.emit('send', 'a@acme.com')
        rig.drain()
        self.assertFalse(rig.hooks.listing('acme.com')['webhooks'][0]['active'])
        self.assertEqual(rig.hooks.emit('send', 'a@acme.com'), 0)
        on = rig.hooks.action('webhook_set_active', {'id': made['id'], 'active': True}, 'acme.com')['webhooks'][0]
        self.assertEqual((on['active'], on['failures']), (True, 0))

    def test_address_that_turns_private_later_is_not_posted_to(self):
        rig = Rig(); rig.add(); rig.hooks.is_public = lambda host: False
        rig.hooks.emit('send', 'a@acme.com'); rig.drain()
        self.assertEqual(rig.sent, [])

    def test_ping(self):
        rig = Rig(answers=[204]); made = rig.add()
        out = rig.hooks.action('webhook_test', {'id': made['id']}, 'acme.com')
        self.assertEqual((out['ok'], out['status'], json.loads(rig.sent[0][2])['type']), (True, 204, 'ping'))


if __name__ == '__main__': unittest.main()
