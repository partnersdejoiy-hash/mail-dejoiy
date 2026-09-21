# Theme backgrounds

The 11 scenic themes currently use pure-CSS gradient art (see `css/themes.css`),
so the app works with zero image files.

To use real photos: drop JPGs here named exactly

```
theme-nightlandscape.jpg   theme-roadtrip.jpg      theme-sunsetaussie.jpg
theme-lighthouse.jpg       theme-spring.jpg        theme-winter.jpg
theme-summer.jpg           theme-galaxy.jpg        theme-fall.jpg
theme-western.jpg          theme-sunset.jpg
```

then add to `css/themes.css`, e.g.:

```css
[data-theme="galaxy"]{ --scenic: url("../assets/themes/theme-galaxy.jpg") center/cover; }
```

Users can also upload their own photo from the theme picker (stored in the
browser via localStorage) — no files needed for that.
