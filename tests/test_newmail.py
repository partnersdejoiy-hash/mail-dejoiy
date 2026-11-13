import sys, tempfile, unittest, xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import webhooks as w, zimbra as z
from newmail import NewMailWatcher


def rig(events=('mail.received',)):
    hooks = w.Webhooks(Path(tempfile.mkdtemp()) / 'webhooks.json', is_public=lambda host: True, post=lambda *a: 200)
    hooks.action('webhook_add', {'url': 'https://hooks.acme.com/in', 'events': list(events)}, 'acme.com')
    boxes = {'asha@acme.com': [{'id': '10', 'date': 1000, 'from': 'old@shop.in'}]}
    watcher = NewMailWatcher(hooks, lambda domain: list(boxes) if domain == 'acme.com' else [], lambda email: boxes[email])
    return hooks, boxes, watcher

def notes(hooks):
    out = []
    while not hooks.jobs.empty(): out.append(hooks.jobs.get()[2])
    return out


class Watching(unittest.TestCase):
    def test_mail_already_there_is_not_news_but_the_next_one_is(self):
        hooks, boxes, watcher = rig()
        self.assertEqual(watcher.check(), 0)
        boxes['asha@acme.com'] = [{'id': '12', 'date': 3000, 'from': 'b@shop.in'}, {'id': '11', 'date': 2000, 'from': 'a@shop.in'}] + boxes['asha@acme.com']
        self.assertEqual(watcher.check(), 2)
        got = notes(hooks)
        self.assertEqual([(n['type'], n['domain'], n['target'], n['actor'], n['message']) for n in got],
                         [('mail.received', 'acme.com', 'asha@acme.com', 'a@shop.in', '11'), ('mail.received', 'acme.com', 'asha@acme.com', 'b@shop.in', '12')])
        self.assertFalse({'subject', 'body', 'text'} & set(got[0]))
        self.assertEqual(watcher.check(), 0)                      # nothing is reported twice

    def test_nobody_asked_means_no_mailbox_is_read(self):
        hooks, boxes, watcher = rig(events=['mail.sent'])
        watcher.inbox = lambda email: self.fail('read a mailbox nobody asked about')
        self.assertEqual(watcher.check(), 0)

    def test_a_mailbox_that_cannot_be_read_keeps_its_place(self):
        hooks, boxes, watcher = rig(); watcher.check()
        good = watcher.inbox
        def broken(email): raise OSError('mail store busy')
        watcher.inbox = broken; self.assertEqual(watcher.check(), 0)
        boxes['asha@acme.com'].insert(0, {'id': '11', 'date': 2000, 'from': 'a@shop.in'})
        watcher.inbox = good; self.assertEqual(watcher.check(), 1)

    def test_watching_again_later_does_not_report_old_mail(self):
        hooks, boxes, watcher = rig(); watcher.check()
        hook = hooks.listing('acme.com')['webhooks'][0]['id']
        hooks.action('webhook_set_active', {'id': hook, 'active': False}, 'acme.com')
        boxes['asha@acme.com'].insert(0, {'id': '11', 'date': 2000, 'from': 'a@shop.in'}); watcher.check()
        hooks.action('webhook_set_active', {'id': hook, 'active': True}, 'acme.com')
        self.assertEqual(watcher.check(), 0)


class ZimbraSide(unittest.TestCase):
    def test_inbox_heads_reads_id_date_and_sender_only(self):
        asked = []
        class Fake:
            def call(self, request, token):
                asked.append((request.find('{%s}query' % z.MAIL).text, request.get('limit'), token))
                return ET.fromstring(f'<SearchResponse xmlns="{z.MAIL}"><m id="257" d="1794600000000"><e t="t" a="asha@acme.com"/><e t="f" a="pay@shop.in"/><su>Secret subject</su></m><m id="9" d="bad"/></SearchResponse>')
        self.assertEqual(z.inbox_heads(Fake(), 'tok'), [{'id': '257', 'date': 1794600000000, 'from': 'pay@shop.in'}])
        self.assertEqual(asked, [('in:inbox', '20', 'tok')])


if __name__ == '__main__': unittest.main()
