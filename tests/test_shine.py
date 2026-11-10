"""Sign-in tokens Dejoiy Mail hands to Shine."""
import base64, hashlib, hmac, json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

def parts(token):
    body, sig = token.split('.')
    pad = lambda s: s + '=' * (-len(s) % 4)
    return body, sig, json.loads(base64.urlsafe_b64decode(pad(body)))

class ShineTokenTests(unittest.TestCase):
    def test_signed_with_shared_secret_and_expires(self):
        body, sig, claims = parts(z.shine_token('s3cret', 'Deepak@Corp.Dejoiy.com', 'Deepak', 'platform', 'https://mail.dejoiy.com/api/avatar?email=x&v=1', now=1000, ttl=120))
        good = base64.urlsafe_b64encode(hmac.new(b's3cret', body.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
        self.assertEqual(sig, good)
        self.assertEqual(claims['e'], 'deepak@corp.dejoiy.com'); self.assertEqual(claims['a'], 'platform'); self.assertTrue(claims['p'].endswith('v=1')); self.assertEqual(claims['x'], 1120000)
        self.assertNotIn('=', body + sig)

    def test_each_token_is_different(self):
        self.assertNotEqual(z.shine_token('k', 'a@b.in', ''), z.shine_token('k', 'a@b.in', ''))

    def test_admin_level_follows_zimbra(self):
        self.assertEqual(z.shine_admin({'isAdmin': True, 'canManageRoles': True}), 'platform')
        self.assertEqual(z.shine_admin({'isAdmin': True, 'canManageRoles': False}), 'company')
        self.assertEqual(z.shine_admin({'isAdmin': False}), '')
        self.assertEqual(z.shine_admin({}), '')

    def test_return_path_stays_on_shine(self):
        for bad in ('https://evil.example', '//evil.example', '', 'javascript:alert(1)', '/a b'):
            self.assertEqual(z.safe_return(bad), '/app/chats')
        self.assertEqual(z.safe_return('/app/chats/c1?embed=1'), '/app/chats/c1?embed=1')

class DirectoryTests(unittest.TestCase):
    def handler(self, auth, secret='k', accounts=''):
        import xml.etree.ElementTree as ET
        class Admin:
            def call(self, request, token): return ET.fromstring('<GetAllAccountsResponse xmlns="urn:zimbraAdmin">' + accounts + '</GetAllAccountsResponse>')
        class Prov: admin = Admin(); token = lambda self: 't'
        class Avatars: versions = lambda self, domain: {'a@x.in': 5}
        h = z.Handler.__new__(z.Handler)
        h.headers = {'Authorization': auth}
        h.server = type('S', (), {'shine_secret': secret, 'provisioner': Prov(), 'avatars': Avatars(), 'app_origin': 'https://mail.dejoiy.com'})()
        return h

    def test_needs_the_shared_secret(self):
        for auth in ('', 'Bearer nope', 'k'):
            with self.assertRaises(z.APIError): self.handler(auth).shine_directory()

    def test_lists_people_with_admin_level_and_photo(self):
        accounts = ('<account name="a@x.in"><a n="displayName">Asha</a><a n="zimbraIsDelegatedAdminAccount">TRUE</a></account>'
                    '<account name="b@x.in"><a n="zimbraAccountStatus">locked</a></account>'
                    '<account name="galsync@x.in"></account><account name="r@x.in"><a n="zimbraIsSystemResource">TRUE</a></account>')
        people = self.handler('Bearer k', accounts=accounts).shine_directory()['people']
        self.assertEqual([p['email'] for p in people], ['a@x.in', 'b@x.in'])
        self.assertEqual(people[0]['admin'], 'company'); self.assertTrue(people[0]['photo'].endswith('v=5'))
        self.assertFalse(people[1]['active']); self.assertEqual(people[1]['photo'], '')

class CalendarBridgeTests(unittest.TestCase):
    def handler(self):
        h = z.Handler.__new__(z.Handler)
        h.server = type('S', (), {'zimbra': object()})()
        h.delegated = lambda email: 'tok:' + email
        h.calls = []
        h.cal = lambda fn, *a: h.calls.append((fn.__name__, a[1:])) or {'ok': True, 'invId': '7-6'}
        return h

    def test_saves_lists_and_deletes_for_the_owner(self):
        h = self.handler()
        self.assertEqual(h.shine_calendar({'op': 'save', 'owner': 'Deepak@Corp.Dejoiy.com', 'event': {'title': 'Sync'}})['invId'], '7-6')
        h.shine_calendar({'op': 'list', 'owner': 'a@x.in', 'start': 1, 'end': 2})
        h.shine_calendar({'op': 'delete', 'owner': 'a@x.in', 'event': {'invId': '7-6'}})
        self.assertEqual([c[0] for c in h.calls], ['save_event', 'events', 'delete_event'])
        self.assertEqual(h.calls[0][1][0], 'tok:deepak@corp.dejoiy.com'); self.assertEqual(h.calls[0][1][2], 'deepak@corp.dejoiy.com')

    def test_refuses_bad_requests(self):
        h = self.handler()
        for bad in ({'op': 'save', 'owner': 'nope'}, {'op': 'drop', 'owner': 'a@x.in'}, {'op': 'list', 'owner': 'a@x.in', 'start': 'x'}):
            with self.assertRaises(z.APIError): h.shine_calendar(bad)

class ShineUpdatesTests(unittest.TestCase):
    def test_new_launch_posts_show_once_then_follow_the_team(self):
        out = z.dejoiy_posts({'posts': [{'id': 'joi', 'pinned': True}]})
        self.assertEqual([p['id'] for p in out[:3]], ['shine-launch', 'shine-calendar', 'shine-colours'])
        self.assertEqual([p['id'] for p in out if p.get('pinned')], ['shine-launch'])
        self.assertTrue(all(p['audience'] == 'both' for p in out[:3]))
        # after the team has posted/deleted, a removed launch post stays gone
        self.assertEqual([p['id'] for p in z.dejoiy_posts({'posts': [{'id': 'joi'}], 'seen': z.SEED_UPDATE_IDS})], ['joi'])

if __name__ == '__main__': unittest.main()
