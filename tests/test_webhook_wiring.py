"""Webhooks wired into the mail app: who may manage them, for which domain, and every audit line feeds them."""
import os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z
import webhooks as w

A = '{urn:zimbraAdmin}'

class Client:
    def __init__(self, perms=None, domains=('acme.com', 'other.com')):
        self.perms, self.domains = perms, domains
    def actor_perms(self, token, actor, scope): return self.perms
    def call(self, r, token=None, timeout=None):
        out = ET.Element(A+'GetDomainResponse')
        name = r.find(A+'domain').text
        if name in self.domains: ET.SubElement(out, A+'domain', {'name': name, 'id': 'x'*36})
        return out

def handler(scope=None, perms=None, actor='boss@acme.com'):
    tmp = tempfile.TemporaryDirectory()
    sent = []
    hooks = w.Webhooks(Path(tmp.name)/'webhooks.json', is_public=lambda host: True, post=lambda u, hd, b: sent.append((u, hd, b)) or 200, sleep=lambda s: None)
    logged = []
    h = SimpleNamespace(server=SimpleNamespace(hooks=hooks, audit=None), _tmp=tmp, sent=sent, logged=logged)
    h.admin_session = lambda s: (Client(perms), 'tok', scope)
    h.log = lambda kind, actor_, target='', n=1: logged.append((kind, actor_, target))
    h.client_ip = lambda: '127.0.0.1'
    h.act = lambda data: z.Handler.webhook_action(h, {'user': {'email': actor}}, data)
    return h

class Wiring(unittest.TestCase):
    def test_company_admin_only_reaches_own_domain(self):
        h = handler(scope='acme.com', perms={'roles.manage'})
        out = h.act({'op': 'webhook_add', 'domain': 'other.com', 'url': 'https://hooks.acme.com/in', 'events': ['mail.sent']})
        self.assertEqual(out['domain'], 'acme.com')
        self.assertEqual(h.act({'op': 'webhooks_get', 'domain': 'other.com'})['domain'], 'acme.com')
        self.assertEqual(h.server.hooks.listing('other.com')['webhooks'], [])

    def test_needs_the_domain_settings_permission(self):
        h = handler(scope='acme.com', perms={'mailboxes.manage'})
        with self.assertRaisesRegex(z.APIError, 'does not allow'): h.act({'op': 'webhooks_get'})

    def test_platform_admin_picks_a_real_domain(self):
        h = handler(scope=None, perms=None, actor='root@mail.dejoiy.com')
        self.assertEqual(h.act({'op': 'webhooks_get', 'domain': 'other.com'})['domain'], 'other.com')
        with self.assertRaisesRegex(z.APIError, 'Domain not found'): h.act({'op': 'webhooks_get', 'domain': 'nope.com'})
        with self.assertRaisesRegex(z.APIError, 'Choose a domain'): h.act({'op': 'webhooks_get'})

    def test_webhook_error_reaches_the_admin_and_secret_is_not_logged(self):
        h = handler(scope='acme.com', perms=None)
        with self.assertRaisesRegex(z.APIError, 'https://'): h.act({'op': 'webhook_add', 'url': 'http://x.com', 'events': ['mail.sent']})
        out = h.act({'op': 'webhook_add', 'url': 'https://hooks.acme.com/in', 'events': ['mail.sent']})
        self.assertTrue(out['secret'].startswith('whsec_'))
        self.assertEqual(h.logged[-1][0], 'admin:webhook_add')
        self.assertNotIn(out['secret'], repr(h.logged))
        self.assertNotIn('secret', h.act({'op': 'webhooks_get'})['webhooks'][0])
        h.act({'op': 'webhooks_get'}); self.assertEqual(len(h.logged), 1)  # looking is not logged

    def test_every_audit_line_feeds_the_webhooks(self):
        h = handler(scope='acme.com')
        hook = h.act({'op': 'webhook_add', 'url': 'https://hooks.acme.com/in', 'events': ['mail.sent']})
        z.Handler.log(h, 'send', 'ravi@acme.com', '2 recipients', 2)
        z.Handler.log(h, 'signin', 'ravi@acme.com')      # not asked for
        z.Handler.log(h, 'send', 'x@other.com', '', 1)    # another company
        self.assertEqual(h.server.hooks.jobs.qsize(), 1)
        h.server.hooks.work_one()
        url, headers, body = h.sent[0]
        self.assertIn(b'"type":"mail.sent"', body)
        stamp = headers['X-Dejoiy-Signature'].split(',')[0][2:]
        self.assertTrue(w.verify(hook['secret'], headers['X-Dejoiy-Signature'], body, now=int(stamp)))

    def test_log_never_breaks_when_hooks_fail(self):
        h = handler()
        h.server.hooks = SimpleNamespace(emit=lambda *a: 0)
        z.Handler.log(h, 'send', 'ravi@acme.com')
        self.assertEqual(z.webhook_domain('Acme.com', 'evil.com'), 'acme.com')

if __name__ == '__main__':
    unittest.main()
