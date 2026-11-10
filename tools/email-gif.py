"""Joins the frames from email-art.cjs into small looping GIFs in web/assets/mail."""
import glob, os
from PIL import Image
here = os.path.dirname(os.path.abspath(__file__)); frames = os.path.join(here, '..', '.email-frames')
for key in sorted({os.path.basename(f).rsplit('_', 1)[0] for f in glob.glob(os.path.join(frames, '*_*.png'))}):
    shots = [Image.open(f).convert('RGB').resize((900, 225), Image.LANCZOS) for f in sorted(glob.glob(os.path.join(frames, key + '_*.png')))]
    palette = shots[0].quantize(colors=32, method=Image.Quantize.MEDIANCUT)
    gif = [s.quantize(palette=palette, dither=Image.Dither.NONE) for s in shots]
    target = os.path.join(here, '..', 'web', 'assets', 'mail', f'banner-{key}.gif')
    gif[0].save(target, save_all=True, append_images=gif[1:], duration=80, loop=0, optimize=True, disposal=1)
    print(key, os.path.getsize(target)//1024, 'KB')
