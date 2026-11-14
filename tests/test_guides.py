"""The user and admin guides: made into safe pages, kept up to date, and served on both sites."""
import importlib.util, sys, threading, unittest, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_guides', ROOT / 'tools' / 'build-guides.py')
guides = importlib.util.module_from_spec(spec); spec.loader.exec_module(guides)
sys.path.insert(0, str(ROOT / 'server'))
import zimbra as z


class RenderTests(unittest.TestCase):
    def test_nothing_in_a_guide_becomes_html_of_its_own(self):
        body, _, _ = guides.render('Hi <script>alert(1)</script> & <img src=x onerror=y>\n\n`<b>code</b>`')
        self.assertNotIn('<script', body); self.assertNotIn('<img', body); self.assertNotIn('<b>', body)
        self.assertIn('&lt;script&gt;', body); self.assertIn('<code>&lt;b&gt;code&lt;/b&gt;</code>', body)

    def test_links_go_only_to_safe_places(self):
        body, _, _ = guides.render('[a](javascript:void) [b](https://dejoiy.com) [c](//evil.example) [d](ADMIN-GUIDE.md#roles) [e](/#/bug)')
        self.assertNotIn('javascript:', body); self.assertNotIn('//evil.example', body)
        self.assertIn('<a href="https://dejoiy.com">b</a>', body)
        self.assertIn('<a href="/help/admin-guide.html#roles">d</a>', body)
        self.assertIn('<a href="/#/bug">e</a>', body)
        self.assertNotIn('>a</a>', body); self.assertTrue(body.startswith('<p>a '))   # an unsafe link keeps only its text

    def test_bug_box_gets_its_button_and_lists_nest(self):
        body, title, toc = guides.render('# Guide\n\n> Something wrong? Use Report a bug.\n\n## Steps\n\n1. One\n   - inner\n2. Two\n\n| A | B |\n|---|---|\n| 1 | 2 |')
        self.assertEqual(title, 'Guide'); self.assertEqual(toc, [('Steps', 'steps')])
        self.assertIn('<aside class="bug-box">', body); self.assertIn('data-report-bug', body)
        self.assertIn('<ol>\n<li>One\n<ul>\n<li>inner</li>\n</ul></li>\n<li>Two</li>\n</ol>', body)
        self.assertIn('<td>1</td><td>2</td>', body)

    def test_both_guides_start_and_end_with_the_bug_box_and_pages_are_current(self):
        for name in guides.GUIDES:
            text = (ROOT / 'docs' / name).read_text().strip()
            self.assertTrue(text.split('\n\n')[1].startswith('> **Found a bug'), name)
            self.assertTrue(text.split('\n\n')[-1].startswith('> **Found a bug'), name)
        self.assertEqual(guides.main(check=True), 0, 'run: python3 tools/build-guides.py')


class ServedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = z.ThreadingHTTPServer(('127.0.0.1', 0), z.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port); cls.server.app_origin = 'https://mail.example'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()

    def get(self, path, host):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args): return None
        req = urllib.request.Request(self.url + path, headers={'Host': host})
        try:
            with urllib.request.build_opener(NoRedirect).open(req) as r: return r.status, r.read().decode()
        except urllib.error.HTTPError as e: return e.code, ''

    def test_guides_open_on_the_mail_site_and_the_admin_site(self):
        for host in ('mail.example', 'admin-mail.example'):
            for page, words in (('user-guide.html', 'User guide'), ('admin-guide.html', 'Admin guide')):
                status, body = self.get('/help/' + page, host)
                self.assertEqual(status, 200, host + page); self.assertIn(words, body); self.assertNotIn('<script', body)
        self.assertEqual(self.get('/settings.html', 'admin-mail.example')[0], 302)   # other pages still go to the mail site


if __name__ == '__main__': unittest.main()
