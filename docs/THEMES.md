# Theme system guide

## 24 themes

**13 colour themes:** AOL Classic, Yellow, High Contrast, Simple, AIM, AOL.com,
Purple, Sunrise, Aqua Green, Aqua Blue, Deep Purple, Blue Night, Dark Grey.

**11 scenic themes** (gradient art today, photos optional): Night Landscape,
Road Trip, Sunset Aussie, Lighthouse, Spring, Winter, Summer, Galaxy, Fall,
Western, Sunset.

## How it works

- `Themes.ALL` in `js/themes.js` defines every theme: `{id, name, kind}`.
- `css/themes.css` maps `html[data-theme="…"]` to `--hdr1/--hdr2/--accent/--scenic`.
- Brightness (`light`/`medium`/`dark`) is a separate `data-brightness` attribute —
  fully independent of theme.
- Themes apply **instantly on click** — no save button.
- Users can upload their own photo background from the picker; it is stored in
  the browser and overrides the theme's scenic art.
- Choice persists in localStorage (`dmail-v1` → `prefs.theme`).

## Adding a theme

1. Add `{id:"mytheme", name:"My Theme", kind:"color"}` to `Themes.ALL`.
2. Add a `[data-theme="mytheme"]` block in `css/themes.css` with `--hdr1`,
   `--hdr2`, `--accent` (and `--scenic` for scenic kinds).
3. Add a swatch entry in `themeSwatch()` in `js/view-settings.js`.
4. Re-run `node --check` on the edited file.
