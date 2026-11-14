#!/usr/bin/env python3
"""Turns the two guides in docs/ into plain, safe web pages the apps can show.

    python3 tools/build-guides.py           # writes web/help/user-guide.html and web/help/admin-guide.html
    python3 tools/build-guides.py --check   # fails when a page is older than its guide (the tests run this)

Only a small part of Markdown is understood: headings, paragraphs, lists (one level of nesting),
quotes, tables, rules, `code`, **bold**, *italic* and links. Every character of the guide is escaped
first, so nothing in a guide can become HTML of its own; links go only to web pages, mail addresses,
places on the same site and the other guide. No scripts on the page.

A quote that mentions "Report a bug" gets a Report a bug button. It opens the mail app's
Report a bug dialog (/#/bug); inside the mail app the dialog opens without leaving the page.
"""
import html, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = {'USER-GUIDE.md': ('user-guide.html', 'User guide'), 'ADMIN-GUIDE.md': ('admin-guide.html', 'Admin guide')}
BUG_LINK = '/#/bug'
SAFE_URL = re.compile(r'^(https?://|mailto:|/|#)', re.I)


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'section'


def href(url):
    """Where a link may go, or None (then only its text is shown)."""
    url = html.unescape(url).strip()
    for name, (page, _) in GUIDES.items():   # one guide links to the other
        if url == name or url.startswith(name + '#') or url == 'docs/' + name or url.startswith('docs/' + name + '#'):
            return '/help/' + page + url.partition('#')[1] + url.partition('#')[2]
    if not SAFE_URL.match(url) or url.startswith('//') or any(c in url for c in '<>"\'` \\') : return None
    return url


def inline(text):
    """One line of guide text as HTML. The text is escaped before anything else happens."""
    codes = []
    def keep(m):
        codes.append('<code>' + html.escape(m.group(1), quote=True) + '</code>')
        return f'\x00{len(codes) - 1}\x00'
    text = re.sub(r'`([^`]+)`', keep, text.replace('\x00', ''))   # code is escaped on its own and put back at the end
    text = html.escape(text, quote=True)
    def link(m):
        target = href(m.group(2))
        if target is None: return m.group(1)
        return f'<a href="{html.escape(target, quote=True)}">{m.group(1)}</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', link, text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', text)
    return re.sub(r'\x00(\d+)\x00', lambda m: codes[int(m.group(1))], text)


def render(markdown):
    """The guide's body as HTML, and its title and sections (for the contents list)."""
    lines = markdown.replace('\r\n', '\n').split('\n')
    out, toc, title, i = [], [], '', 0
    def para(buf):
        if buf: out.append('<p>' + inline(' '.join(s.strip() for s in buf)) + '</p>')
    while i < len(lines):
        line = lines[i]
        if not line.strip(): i += 1; continue
        m = re.match(r'^(#{1,4})\s+(.*?)\s*#*\s*$', line)
        if m:
            level, text = len(m.group(1)), m.group(2)
            ident = slug(text); n = 2
            while any(ident == t[1] for t in toc) or ident == 'contents': ident = f'{slug(text)}-{n}'; n += 1
            if level == 1 and not title: title = text
            if level == 2: toc.append((text, ident))
            else: toc.append(('', ident))
            out.append(f'<h{level} id="{ident}">{inline(text)}</h{level}>'); i += 1; continue
        if re.match(r'^\s*(-{3,}|\*{3,})\s*$', line): out.append('<hr>'); i += 1; continue
        if line.startswith('>'):
            buf = []
            while i < len(lines) and lines[i].startswith('>'): buf.append(lines[i][1:].strip()); i += 1
            parts, cur = [], []
            for s in buf:
                if s: cur.append(s)
                elif cur: parts.append(cur); cur = []
            if cur: parts.append(cur)
            body = ''.join('<p>' + inline(' '.join(p)) + '</p>' for p in parts)
            if 'Report a bug' in ' '.join(buf):
                out.append(f'<aside class="bug-box">{body}<p><a class="bug-btn" href="{BUG_LINK}" data-report-bug>Report a bug</a></p></aside>')
            else: out.append(f'<blockquote>{body}</blockquote>')
            continue
        if line.lstrip().startswith('|'):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-{2,}:?', c) for c in cells): rows.append(cells)
                i += 1
            head, *body = rows
            out.append('<div class="table"><table><thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in head) + '</tr></thead><tbody>'
                       + ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>' for r in body) + '</tbody></table></div>')
            continue
        item = re.compile(r'^(\s*)([-*]|\d+[.)])\s+(.*)$')
        if item.match(line):
            stack = []   # (indent, tag)
            while i < len(lines):
                m = item.match(lines[i])
                if not m:
                    if lines[i].strip() and lines[i].startswith('  ') and stack:   # a wrapped line of the same item
                        out[-1] = out[-1][:-5] + ' ' + inline(lines[i].strip()) + '</li>'; i += 1; continue
                    break
                indent, tag = len(m.group(1)), 'ol' if m.group(2)[0].isdigit() else 'ul'
                if not stack or indent > stack[-1][0]:
                    if stack: out[-1] = out[-1][:-5]   # the new list sits inside the item above
                    out.append(f'<{tag}>'); stack.append((indent, tag))
                else:
                    while len(stack) > 1 and indent < stack[-1][0]:
                        out.append(f'</{stack.pop()[1]}></li>')
                out.append('<li>' + inline(m.group(3)) + '</li>'); i += 1
            while stack:
                out.append(f'</{stack.pop()[1]}>' + ('</li>' if stack else ''))
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#{1,4}\s|>|\s*([-*]|\d+[.)])\s|\s*\|)', lines[i]) and not re.match(r'^\s*(-{3,}|\*{3,})\s*$', lines[i]):
            buf.append(lines[i]); i += 1
        para(buf)
    return '\n'.join(out), title, [t for t in toc if t[0]]


PAGE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Dejoiy Mail</title>
<meta name="color-scheme" content="light dark">
<style>
:root{{--bg:#f7f7f9;--card:#fff;--ink:#1d1d24;--muted:#5b5b68;--line:#e2e2ea;--accent:#5b3cc4;--accent-ink:#fff;--soft:#f0ecfd}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121218;--card:#1b1b23;--ink:#ececf2;--muted:#a9a9b8;--line:#2e2e3a;--accent:#a48cff;--accent-ink:#14121c;--soft:#251f3d}}}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}}
.guide{{max-width:46rem;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:1.9rem;line-height:1.2;margin:.2em 0 .6em}}
h2{{font-size:1.4rem;line-height:1.3;margin:2em 0 .5em;padding-top:.6em;border-top:1px solid var(--line)}}
h3{{font-size:1.15rem;margin:1.6em 0 .4em}}
h4{{font-size:1rem;margin:1.2em 0 .3em}}
p,li{{max-width:100%}}
ul,ol{{padding-left:1.4em}}
li{{margin:.25em 0}}
a{{color:var(--accent)}}
code{{font:.92em ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--soft);padding:.1em .35em;border-radius:5px}}
hr{{border:0;border-top:1px solid var(--line);margin:2em 0}}
blockquote{{margin:1em 0;padding:.6em 1em;border-left:4px solid var(--line);color:var(--muted)}}
.bug-box{{margin:1.2em 0;padding:14px 16px;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:10px;background:var(--card)}}
.bug-box p{{margin:.4em 0}}
.bug-btn{{display:inline-block;margin-top:.3em;padding:.55em 1.1em;border-radius:999px;background:var(--accent);color:var(--accent-ink);font-weight:600;text-decoration:none}}
.toc{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px}}
.toc p{{margin:.3em 0;font-weight:600}}
.table{{overflow-x:auto;margin:1em 0}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid var(--line);padding:.45em .6em;text-align:left;vertical-align:top}}
th{{background:var(--soft)}}
</style>
</head>
<body>
<main class="guide" id="guide">
{body}
</main>
</body>
</html>
'''


def page(markdown):
    body, title, toc = render(markdown)
    if toc:   # a contents list under the title (and the box under it)
        listing = '<nav class="toc" aria-label="Contents"><p>Contents</p><ul>' + ''.join(f'<li><a href="#{i}">{inline(t)}</a></li>' for t, i in toc) + '</ul></nav>'
        first_h2 = body.find('<h2 ')
        body = body[:first_h2] + listing + '\n' + body[first_h2:] if first_h2 >= 0 else body + listing
    return PAGE.format(title=html.escape(title or 'Guide'), body=body)


def main(check=False):
    stale = []
    for name, (target, _) in GUIDES.items():
        source, dest = ROOT / 'docs' / name, ROOT / 'web' / 'help' / target
        text = page(source.read_text(encoding='utf-8'))
        if check:
            if not dest.exists() or dest.read_text(encoding='utf-8') != text: stale.append(f'{dest.relative_to(ROOT)} is older than docs/{name}')
        else:
            dest.parent.mkdir(exist_ok=True); dest.write_text(text, encoding='utf-8'); print('wrote', dest.relative_to(ROOT))
    if stale: print('\n'.join(stale) + '\nRun: python3 tools/build-guides.py', file=sys.stderr); return 1
    return 0


if __name__ == '__main__': sys.exit(main('--check' in sys.argv))
