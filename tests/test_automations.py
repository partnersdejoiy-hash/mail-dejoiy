"""Ready-made automations: Important mail to Shine. Matching, what the post says, limits, and one company never reaching another."""
import os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import automations as au
import webhooks as w
import zimbra as z
from newmail import NewMailWatcher

A = '{urn:zimbraAdmin}'


class Audit:
    def __init__(self): self.lines = []
    def add(self, kind, actor, target='', ip='', n=1): self.lines.append((kind, actor, target))


def rig(post=None, clock=None):
    posted, audit = [], Audit()
    def default(payload): posted.append(payload); return {'ok': True}
    autos = au.Automations(Path(tempfile.mkdtemp()) / 'automations.json', post or default, audit, **({'clock': clock} if clock else {}))
    return autos, posted, audit


def turn_on(autos, domain='acme.com', senders='ceo@client.com\n@bank.com', channel='#urgent', subject=False, actor='boss@acme.com'):
    return autos.action('automation_save', {'kind': 'important_to_shine', 'settings': {'on': True, 'senders': senders, 'channel': channel, 'subject': subject}}, domain, actor)


def drain(autos):
    while not autos.jobs.empty(): autos.work_one()


class Settings(unittest.TestCase):
    def test_saved_and_listed(self):
        autos, _, _ = rig()
        out = turn_on(autos)['important_to_shine']
        self.assertEqual((out['on'], out['senders'], out['channel'], out['by']), (True, ['ceo@client.com', '@bank.com'], 'urgent', 'boss@acme.com'))
        self.assertEqual(au.Automations(autos.path, lambda p: None).listing('acme.com')['important_to_shine']['senders'], ['ceo@client.com', '@bank.com'])
        self.assertEqual(autos.domains(), {'acme.com'})

    def test_what_the_admin_must_give(self):
        autos, _, _ = rig()
        with self.assertRaisesRegex(au.AutomationError, 'not an address'): turn_on(autos, senders='hello')
        with self.assertRaisesRegex(au.AutomationError, 'at least one sender'): turn_on(autos, senders='')
        with self.assertRaisesRegex(au.AutomationError, 'channel'): turn_on(autos, channel='')
        with self.assertRaisesRegex(au.AutomationError, 'up to 50'): turn_on(autos, senders=' '.join(f'a{i}@x.com' for i in range(51)))
        with self.assertRaisesRegex(au.AutomationError, 'Unknown automation'): autos.action('automation_save', {'kind': 'rm -rf'}, 'acme.com', 'a@acme.com')
        # switched off it may be saved half-filled
        autos.action('automation_save', {'kind': 'important_to_shine', 'settings': {'on': False}}, 'acme.com', 'a@acme.com')
        self.assertEqual(autos.domains(), set())

    def test_sender_matching(self):
        senders = ['ceo@client.com', '@bank.com']
        self.assertTrue(au.sender_matches('CEO@Client.com', senders))
        self.assertTrue(au.sender_matches('alerts@bank.com', senders))
        for no in ('ceo@client.com.evil.io', 'x@evilbank.com', 'x@bank.com.in', '', None, 'other@client.com'):
            self.assertFalse(au.sender_matches(no, senders), no)


class Posting(unittest.TestCase):
    def test_matching_mail_posts_who_and_where_but_not_the_subject(self):
        autos, posted, audit = rig(); turn_on(autos)
        self.assertTrue(autos.new_mail('acme.com', 'asha@acme.com', {'id': '5', 'from': 'alerts@bank.com', 'subject': 'Salary credited'}))
        self.assertFalse(autos.new_mail('acme.com', 'asha@acme.com', {'id': '6', 'from': 'news@shop.in', 'subject': 'Sale'}))
        drain(autos)
        self.assertEqual(posted, [{'op': 'post', 'scope': 'acme.com', 'actor': 'boss@acme.com', 'channel': 'urgent', 'text': 'Important mail for asha@acme.com from alerts@bank.com'}])
        self.assertEqual(audit.lines, [('automation:important_to_shine', 'asha@acme.com', '#urgent ok')])
        self.assertTrue(autos.listing('acme.com')['important_to_shine']['last']['ok'])

    def test_subject_only_when_switched_on(self):
        autos, posted, audit = rig(); turn_on(autos, subject=True)
        autos.new_mail('acme.com', 'asha@acme.com', {'id': '5', 'from': 'ceo@client.com', 'subject': 'Contract'}); drain(autos)
        self.assertEqual(posted[0]['text'], 'Important mail for asha@acme.com from ceo@client.com\nSubject: Contract')
        self.assertNotIn('Contract', repr(audit.lines))

    def test_switched_off_posts_nothing(self):
        autos, posted, _ = rig(); turn_on(autos)
        autos.action('automation_save', {'kind': 'important_to_shine', 'settings': {'on': False, 'senders': '@bank.com', 'channel': 'urgent'}}, 'acme.com', 'boss@acme.com')
        self.assertFalse(autos.new_mail('acme.com', 'asha@acme.com', {'id': '5', 'from': 'alerts@bank.com'}))

    def test_a_failed_post_is_shown_to_the_admin(self):
        def refuse(payload): raise z.APIError('boss@acme.com (who made this API token) is not a member of #urgent.')
        autos, _, audit = rig(post=refuse); turn_on(autos)
        autos.new_mail('acme.com', 'asha@acme.com', {'id': '5', 'from': 'alerts@bank.com'}); drain(autos)
        last = autos.listing('acme.com')['important_to_shine']['last']
        self.assertFalse(last['ok']); self.assertIn('not a member', last['error'])
        self.assertEqual(audit.lines[-1][2], '#urgent failed')

    def test_a_mail_storm_does_not_flood_the_channel(self):
        now = [1000.0]; autos, posted, _ = rig(clock=lambda: now[0]); turn_on(autos)
        sent = sum(autos.new_mail('acme.com', 'asha@acme.com', {'id': str(i), 'from': 'alerts@bank.com'}) for i in range(100))
        self.assertEqual(sent, au.POSTS_PER_HOUR)
        now[0] += 3601
        self.assertTrue(autos.new_mail('acme.com', 'asha@acme.com', {'id': 'x', 'from': 'alerts@bank.com'}))


class WithTheWatcher(unittest.TestCase):
    def setUp(self):
        self.hooks = w.Webhooks(Path(tempfile.mkdtemp()) / 'webhooks.json', is_public=lambda host: True, post=lambda *a: 200)
        self.autos, self.posted, _ = rig()
        self.boxes = {'asha@acme.com': [{'id': '1', 'date': 1, 'from': 'x@y.com', 'subject': 'old'}],
                      'ravi@other.com': [{'id': '1', 'date': 1, 'from': 'x@y.com', 'subject': 'old'}]}
        self.read = []
        def inbox(email): self.read.append(email); return self.boxes[email]
        self.watcher = NewMailWatcher(self.hooks, lambda d: [b for b in self.boxes if b.endswith('@' + d)], inbox, listeners=[self.autos])

    def arrive(self, box, mid, sender, subject='Hello'):
        self.boxes[box] = [{'id': mid, 'date': int(mid) * 10, 'from': sender, 'subject': subject}] + self.boxes[box]

    def test_an_automation_alone_makes_the_watcher_look_at_only_that_company(self):
        turn_on(self.autos)
        self.watcher.check(); self.assertEqual(set(self.read), {'asha@acme.com'})
        self.arrive('asha@acme.com', '7', 'alerts@bank.com'); self.arrive('ravi@other.com', '7', 'alerts@bank.com')
        self.watcher.check(); drain(self.autos)
        self.assertEqual([p['text'] for p in self.posted], ['Important mail for asha@acme.com from alerts@bank.com'])
        self.assertNotIn('ravi@other.com', self.read)
        self.assertTrue(self.hooks.jobs.empty())   # no webhook asked, so no note

    def test_each_company_posts_only_in_its_own_scope(self):
        turn_on(self.autos, domain='acme.com', channel='urgent', actor='boss@acme.com')
        turn_on(self.autos, domain='other.com', channel='urgent', actor='chief@other.com')
        self.watcher.check()
        self.arrive('asha@acme.com', '7', 'alerts@bank.com'); self.arrive('ravi@other.com', '8', 'alerts@bank.com')
        self.watcher.check(); drain(self.autos)
        self.assertEqual(sorted((p['scope'], p['actor'], p['text'].split(' for ')[1].split(' ')[0]) for p in self.posted),
                         [('acme.com', 'boss@acme.com', 'asha@acme.com'), ('other.com', 'chief@other.com', 'ravi@other.com')])

    def test_webhook_note_still_never_carries_the_subject(self):
        self.hooks.action('webhook_add', {'url': 'https://hooks.acme.com/in', 'events': ['mail.received']}, 'acme.com')
        turn_on(self.autos, subject=True)
        self.watcher.check(); self.arrive('asha@acme.com', '7', 'ceo@client.com', 'Board minutes')
        self.watcher.check(); drain(self.autos)
        note = self.hooks.jobs.get()[2]
        self.assertNotIn('Board minutes', repr(note))
        self.assertIn('Subject: Board minutes', self.posted[0]['text'])

    def test_a_broken_automation_never_stops_the_webhooks(self):
        self.hooks.action('webhook_add', {'url': 'https://hooks.acme.com/in', 'events': ['mail.received']}, 'acme.com')
        turn_on(self.autos)
        self.autos.new_mail = lambda *a: 1 / 0
        self.watcher.check(); self.arrive('asha@acme.com', '7', 'alerts@bank.com')
        self.assertEqual(self.watcher.check(), 1)


class AdminWiring(unittest.TestCase):
    def handler(self, scope, perms, actor):
        autos, _, _ = rig(); logged = []
        h = SimpleNamespace(server=SimpleNamespace(automations=autos), logged=logged)
        client = SimpleNamespace(actor_perms=lambda t, a, sc: perms, call=lambda r, t=None, timeout=None: (lambda out: (ET.SubElement(out, A + 'domain', {'name': 'x'}), out)[1])(ET.Element(A + 'R')))
        h.admin_session = lambda sess: (client, 'tok', scope)
        h.log = lambda kind, a, target='', n=1: logged.append((kind, a, target))
        h.act = lambda data: z.Handler.automation_action(h, {'user': {'email': actor}}, data)
        return h

    def test_company_admin_only_their_own_domain(self):
        h = self.handler('acme.com', {'roles.manage'}, 'boss@acme.com')
        out = h.act({'op': 'automation_save', 'domain': 'other.com', 'kind': 'important_to_shine', 'settings': {'on': True, 'senders': '@bank.com', 'channel': 'urgent'}})
        self.assertEqual(out['domain'], 'acme.com')
        self.assertEqual(h.server.automations.domains(), {'acme.com'})
        self.assertEqual(h.logged, [('admin:automation_save', 'boss@acme.com', 'acme.com important_to_shine on')])

    def test_needs_the_domain_settings_permission(self):
        h = self.handler('acme.com', {'mailboxes.manage'}, 'boss@acme.com')
        with self.assertRaisesRegex(z.APIError, 'does not allow'): h.act({'op': 'automations_get'})


if __name__ == '__main__': unittest.main()
