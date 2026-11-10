"""Dejoiy Updates and company boxes: who can post where, and what each person sees."""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

def handler(store):
    h = object.__new__(z.Handler); h.server = types.SimpleNamespace(updates=store, provisioner=None); return h
def session(email, admin=False, platform=False):
    return {'user': {'email': email, 'name': email.split('@')[0], 'isAdmin': admin or platform, 'canManageRoles': platform}}

class UpdateTests(unittest.TestCase):
    def setUp(self): self.store = z.AppearanceStore(None, 'updates')

    def test_dejoiy_team_posts_everyone_reads(self):
        handler(self.store).post_update(session('root@dejoiy.com', platform=True), {'box': 'dejoiy', 'op': 'post', 'title': 'New themes', 'body': 'Try them'})
        view = handler(self.store).updates_view(session('priya@kaalitea.in'))
        self.assertEqual(view['dejoiy'][0]['title'], 'New themes'); self.assertEqual(len(view['dejoiy']), len(z.DEFAULT_UPDATES) + 1); self.assertFalse(view['can']['dejoiy'])

    def test_first_visit_shows_default_updates_until_team_edits(self):
        self.assertEqual(handler(self.store).updates_view(session('priya@kaalitea.in'))['dejoiy'][0]['id'], 'welcome')
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

if __name__ == '__main__': unittest.main()
