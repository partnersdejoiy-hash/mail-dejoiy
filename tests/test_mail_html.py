"""Received mail keeps a small, safe part of its own design; nothing that loads, runs or leaves its box."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import zimbra as z

class Styles(unittest.TestCase):
    def test_layout_and_colour_are_kept(self):
        self.assertEqual(z.safe_style('Color:#121212; FONT:600 13px/1.4 "Outfit",Arial,sans-serif; padding-top:4px; border-radius:21px 21px 0 0'),
                         'color:#121212;font:600 13px/1.4 "outfit",arial,sans-serif;padding-top:4px;border-radius:21px 21px 0 0')
        self.assertEqual(z.safe_style('background:linear-gradient(90deg,#fff,#eee);max-width:594px'), 'background:linear-gradient(90deg,#fff,#eee);max-width:594px')

    def test_anything_that_loads_runs_or_escapes_is_dropped(self):
        for bad in ('background:url(https://evil.test/x.png)', 'background-image:url(x)', 'width:expression(alert(1))', 'position:fixed', 'top:0',
                    'z-index:99999', 'margin:-200px', 'margin:0 0 0 -9999px', 'transform:scale(9)', 'behavior:url(x.htc)', 'content:"x"',
                    'display:flex', 'color:red;}body{display:none', 'font-family:\\6a avascript', '-moz-binding:url(x)', 'color:<b>'):
            self.assertNotRegex(z.safe_style(bad), r'url|expression|position|top:|z-index|-\d|transform|behavior|content|flex|\}|\\|binding|<', bad)

    def test_only_received_mail_is_styled(self):
        raw = '<p style="color:#ff0000" onclick="x()">Hi</p>'
        self.assertEqual(z.safe_html(raw), '<p>Hi</p>')
        self.assertEqual(z.safe_html(raw, styled=True), '<div class="mail-html"><p style="color:#ff0000">Hi</p></div>')
        self.assertEqual(z.safe_html('<p>Hi</p>', styled=True), '<p>Hi</p>')        # a plain mail stays in the reader's own colours

    def test_hidden_preview_line_stays_hidden_and_tables_keep_their_shape(self):
        out = z.safe_html('<div style="display:none;max-height:0;overflow:hidden;opacity:0">preview text</div>'
                          '<table width="100%" cellpadding="0" bgcolor="#C8FF2E" onload="x()" background="http://x/y.png"><tr><td align="center" valign="top" width="52" style="padding:8px">A</td></tr></table>', styled=True)
        self.assertIn('<div style="display:none;max-height:0;overflow:hidden;opacity:0">preview text</div>', out)
        self.assertIn('<table width="100%" bgcolor="#c8ff2e" cellpadding="0">', out)
        self.assertIn('<td style="padding:8px" width="52" align="center" valign="top">', out)
        self.assertNotRegex(out, r'onload|background=|http://x')

    def test_scripts_frames_and_event_handlers_never_come_back(self):
        out = z.safe_html('<style>p{color:red}</style><script>alert(1)</script><iframe src="x"></iframe><p style="color:red" onmouseover="x()">ok</p>'
                          '<a href="javascript:alert(1)" style="color:blue">l</a><hr><font color="red" face="x">f</font>', styled=True)
        self.assertNotRegex(out, r'script|iframe|onmouseover|javascript|<style|face=|color="red"')
        self.assertIn('<hr>', out); self.assertIn('<font>f</font>', out); self.assertIn('<a style="color:blue">l</a>', out)

if __name__ == '__main__': unittest.main()
