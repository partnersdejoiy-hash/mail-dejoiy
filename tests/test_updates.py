"""Dejoiy Updates and company boxes: who can post where, and what each person sees."""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

import base64
FILES = z.AppearanceStore(None, 'files')
def handler(store):
    h = object.__new__(z.Handler); h.server = types.SimpleNamespace(updates=store, update_files=FILES, provisioner=None); return h
def session(email, admin=False, platform=False):
    return {'user': {'email': email, 'name': email.split('@')[0], 'isAdmin': admin or platform, 'canManageRoles': platform}}

class UpdateTests(unittest.TestCase):
    def setUp(self): self.store = z.AppearanceStore(None, 'updates')

    def test_dejoiy_team_posts_everyone_reads(self):
        handler(self.store).post_update(session('root@dejoiy.com', platform=True), {'box': 'dejoiy', 'op': 'post', 'title': 'New themes', 'body': 'Try them'})
        view = handler(self.store).updates_view(session('priya@kaalitea.in'))
        self.assertEqual(view['dejoiy'][0]['title'], 'New themes'); self.assertEqual(len(view['dejoiy']), len(z.DEFAULT_UPDATES) + 1); self.assertFalse(view['can']['dejoiy'])

    def test_first_visit_shows_default_updates_until_team_edits(self):
        self.assertIn('welcome', [p['id'] for p in handler(self.store).updates_view(session('priya@kaalitea.in'))['dejoiy']])
        handler(self.store).post_update(session('root@dejoiy.com', platform=True), {'box': 'dejoiy', 'op': 'delete', 'id': 'welcome'})
        ids = [p['id'] for p in handler(self.store).updates_view(session('priya@kaalitea.in'))['dejoiy']]
        self.assertNotIn('welcome', ids); self.assertIn('labels', ids)

    def test_company_admin_cannot_post_dejoiy_updates(self):
        with self.assertRaises(z.APIError): handler(self.store).post_update(session('boss@kaalitea.in', admin=True), {'box': 'dejoiy', 'op': 'post', 'title': 'x', 'body': 'y'})

    def test_company_box_stays_inside_its_company(self):
        handler(self.store).post_update(session('boss@kaalitea.in', admin=True), {'box': 'company', 'op': 'post', 'title': 'Holiday', 'body': 'Office closed'})
        self.assertEqual(handler(self.store).updates_view(session('ravi@kaalitea.in'))['company']['posts'][0]['title'], 'Holiday')
        self.assertEqual(handler(self.store).updates_view(session('anu@other.in'))['company']['posts'], [])
        with self.assertRaises(z.APIError): handler(self.store).post_update(session('ravi@kaalitea.in'), {'box': 'company', 'op': 'post', 'title': 'x', 'body': 'y'})

    def test_files_stay_in_their_company(self):
        png = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'0' * 20).decode()
        view = handler(self.store).post_update(session('boss@kaalitea.in', admin=True), {'box': 'company', 'op': 'post', 'kind': 'event', 'title': 'Diwali party',
            'body': 'Friday 6 pm', 'link': {'url': 'https://example.com/rsvp', 'label': 'RSVP'},
            'files': [{'name': 'poster.png', 'data': png}, {'name': 'agenda.pdf', 'data': base64.b64encode(b'%PDF-1.4').decode()}]})
        post = view['company']['posts'][0]
        self.assertEqual(post['kind'], 'event'); self.assertEqual([f['image'] for f in post['files']], [True, False])
        record = FILES.get('file:' + post['files'][0]['id']); self.assertEqual(record['box'], 'company:kaalitea.in')
        with self.assertRaises(z.APIError): handler(self.store).update_file(session('anu@other.in'), post['files'][0]['id'])

    def test_bad_links_and_big_files_are_refused(self):
        with self.assertRaises(z.APIError):
            handler(self.store).post_update(session('boss@kaalitea.in', admin=True), {'box': 'company', 'op': 'post', 'title': 'x', 'body': 'y', 'link': {'url': 'javascript:alert(1)'}})
        big = base64.b64encode(b'0' * (z.MAX_UPDATE_FILES + 1)).decode()
        with self.assertRaises(z.APIError):
            handler(self.store).post_update(session('boss@kaalitea.in', admin=True), {'box': 'company', 'op': 'post', 'title': 'x', 'body': 'y', 'files': [{'name': 'a', 'data': big}]})

    def test_pin_moves(self):
        h = handler(self.store); boss = session('boss@kaalitea.in', admin=True)
        for t in ('one', 'two'): h.post_update(boss, {'box': 'company', 'op': 'post', 'title': t, 'body': t})
        ids = [p['id'] for p in h.updates_view(boss)['company']['posts']]
        h.post_update(boss, {'box': 'company', 'op': 'pin', 'id': ids[1]})
        self.assertEqual([p['pinned'] for p in h.updates_view(boss)['company']['posts']], [False, True])

if __name__ == '__main__': unittest.main()
