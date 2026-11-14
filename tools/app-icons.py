"""App icons for the Android apps and the web manifests (needs rsvg-convert).
Mail: the :D face on hot pink. Admin: a pink shield on ink with the :D face inside, so the two never look alike on a phone.
Maskable icons keep everything inside the central 80% circle Android may crop to."""
import os, subprocess, tempfile
here = os.path.dirname(os.path.abspath(__file__)); out = os.path.join(here, '..', 'web', 'assets', 'icons')
PINK, INK = '#FF4FA3', '#121212'
FACE = '<circle cx="13" cy="28" r="12" fill="{eye}"/><circle cx="13" cy="72" r="12" fill="{ink}"/><path fill-rule="evenodd" d="M38 0H88A50 50 0 0 1 88 100H38Z M62 26H86A24 24 0 0 1 86 74H62Z" fill="{ink}"/>'
D_SHAPE = '<path d="M18 -20H80A70 70 0 0 1 80 120H18A18 18 0 0 1 0 102V-2A18 18 0 0 1 18 -20Z" fill="{fill}"/>'
SHIELD = '<path d="M0 -26 22 -17V0C22 15 12 24 0 29C-12 24 -22 15 -22 0V-17Z" fill="{fill}"/><path d="M-9 1 -2 8 11 -6" fill="none" stroke="{tick}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'

def face(width, cx, cy, eye='#FFFFFF', ink=INK):
    s = width / 138; return f'<g transform="translate({cx - 69*s} {cy - 50*s}) scale({s})">{FACE.format(eye=eye, ink=ink)}</g>'
def sticker(width, cx, cy, fill=PINK, eye='#FFFFFF', ink=INK):
    s = width / 150; shape = D_SHAPE.format(fill=fill)
    inner = '' if ink is None else f'<g transform="translate(22 17) scale(.66)">{FACE.format(eye=eye, ink=ink)}</g>'
    return f'<g transform="translate({cx - 75*s} {cy - 50*s}) scale({s})">{shape}{inner}</g>'
def badge(cx, cy, r, fill='#FFFFFF', shield=INK, tick=PINK):
    s = r / 34; return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/><g transform="translate({cx} {cy}) scale({s})">{SHIELD.format(fill=shield, tick=tick)}</g>'
GUARD = '<path d="M100 8 188 40V106C188 164 150 202 100 222C50 202 12 164 12 106V40Z" fill="{fill}" stroke="{fill}" stroke-width="16" stroke-linejoin="round"/>'
def guard(width, cx, cy, fill=PINK, eye='#FFFFFF', ink=INK):
    """The admin mark: a shield with the :D face in it. ink=None leaves the face out (the caller cuts it)."""
    s = width / 200; inner = '' if ink is None else face(116, 100, 104, eye, ink)
    return f'<g transform="translate({cx - 100*s} {cy - 115*s}) scale({s})">{GUARD.format(fill=fill)}{inner}</g>'
def cut(shape, hole):
    return f'<defs><mask id="m"><rect width="512" height="512" fill="#000"/>{shape}{hole}</mask></defs><rect width="512" height="512" fill="#FFFFFF" mask="url(#m)"/>'
def svg(body, bg=None, radius=0):
    back = f'<rect width="512" height="512" rx="{radius}" fill="{bg}"/>' if bg else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{back}{body}</svg>'

ICONS = {
    'maskable-512.png': svg(face(270, 256, 256), PINK),
    'monochrome-512.png': svg(face(270, 256, 256, eye='#FFFFFF', ink='#FFFFFF')),
    'admin-512.png': svg(guard(300, 256, 256), INK, 112),
    'admin-maskable-512.png': svg(guard(232, 256, 256), INK),
    'admin-monochrome-512.png': svg(cut(guard(250, 256, 256, fill='#FFFFFF', ink=None), guard(250, 256, 256, fill='none', eye='#000000', ink='#000000'))),
    'shortcut-compose.png': svg('<path d="M150 362 170 290 320 140a28 28 0 0 1 40 0l12 12a28 28 0 0 1 0 40L222 342Z" fill="#121212"/><path d="M140 392h232" stroke="#121212" stroke-width="28" stroke-linecap="round"/>', PINK, 256),
    'shortcut-inbox.png': svg('<path d="M120 270 170 150h172l50 120v92a30 30 0 0 1-30 30H150a30 30 0 0 1-30-30Z M120 270h80l24 44h64l24-44h80" fill="none" stroke="#121212" stroke-width="28" stroke-linejoin="round"/>', '#FFD23F', 256),
    'shortcut-updates.png': svg('<path d="M130 230v52h40l110 70V160L170 230Z" fill="#121212"/><path d="M320 200a80 80 0 0 1 0 112" fill="none" stroke="#121212" stroke-width="26" stroke-linecap="round"/>', '#B892FF', 256),
}
SIZES = {'maskable-512.png': (512, 192), 'admin-512.png': (512, 192), 'admin-maskable-512.png': (512, 192), 'monochrome-512.png': (512,), 'admin-monochrome-512.png': (512,),
         'shortcut-compose.png': (96,), 'shortcut-inbox.png': (96,), 'shortcut-updates.png': (96,)}
with tempfile.TemporaryDirectory() as tmp:
    for name, body in ICONS.items():
        source = os.path.join(tmp, name + '.svg'); open(source, 'w').write(body)
        for size in SIZES[name]:
            target = os.path.join(out, name if size == 512 or name.startswith('shortcut') else name.replace('512', str(size)))
            subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size), source, '-o', target], check=True)
            print(os.path.relpath(target, os.path.join(here, '..')))
