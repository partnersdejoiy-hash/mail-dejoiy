# Architecture — Dejoiy Mail front-end (v0.1)

## Big picture

```
┌─────────────────────────────────────────────┐
│  web/  — static front-end (this repo)       │
│  index.html → css/* → js/* (plain scripts)  │
│  State: Store (localStorage, key dmail-v1)  │
└───────────────┬─────────────────────────────┘
                │  future: REST API
┌───────────────▼─────────────────────────────┐
│  backend — mail servers (see ROADMAP.md)    │
│  WildDuck / Haraka / Rspamd …               │
└─────────────────────────────────────────────┘
```

The front-end is deliberately **dependency-free**: no framework, no bundler, no build.
Every view is a `Views.<name>(el, arg)` render function; `App` owns routing (`#/route:arg`),
dialogs, menus, toasts, keyboard shortcuts and sounds.

## Module map

| File | Responsibility |
|---|---|
| `js/data.js` | Demo content only. Swapped for API calls later. |
| `js/store.js` | Single state object, `save()` → localStorage, helpers (`esc`, `fmtDate`, `uid`, `initials`). |
| `js/themes.js` | 24 theme definitions; `apply()` sets `data-theme`/`data-brightness` on `<html>`; custom photo → `#bg.custom`. |
| `js/filters.js` | Pure filter engine: `matches(email, filter)`, `applyTo(email, filter)`, `runAll()`. No DOM. |
| `js/mail.js` | Mailbox operations + search + simulated incoming mail (`checkMail`). |
| `js/view-*.js` | One file per view. Each renders into `#view` and binds its own events. |
| `js/app.js` | Hash router, nav chrome, dialog/menu/toast primitives, global search, shortcuts, WebAudio sounds. |

## State shape

```js
{
  version: 1,
  user: {name, email, signature},
  emails: [{id, from{name,email}, to[], cc[], subject, body(html), date, folder,
            read, starred, important, labels[], hasAttachment, attachments[{name,size}]}],
  contacts: [{id, name, email, phone, org, presence}],
  events: [{id, title, date(yyyy-mm-dd), time, notes}],
  todos: [{id, text, done}],
  notes: [{id, title, body, ts}],
  chats: {contactId: [{from:'me'|'them', text, ts}]},
  filters: [{id, name, on, criteria{...}, actions{...}}],
  blocked: [email], allowed: [email],
  vacation: {on, subject, message},
  prefs: {theme, brightness, customBg(dataURL), sounds},
  admin: {org, users[{name,email,role}], domains[{domain,mx,spf,dkim,dmarc}]},
  poolIdx: Number
}
```

## Theming

- `css/themes.css` maps `html[data-theme="…"]` → `--hdr1/--hdr2/--accent/--scenic`.
- `html[data-brightness]` → surface/ink tokens (independent of theme).
- Scenic themes are gradient art today; drop real photos into `web/assets/themes/`
  and reference them (see `docs/THEMES.md`).

## Responsive strategy

Pure CSS breakpoints + tiny body-class toggles:
- `>900px` desktop: sidebar + 3-pane mail.
- `≤900px` tablet: 2-pane mail (list + reader).
- `≤680px` phone: single pane, bottom nav, `body.reader-open` / `body.chat-open` switch panes.

## Conventions

- Never leave a dead button: every control does something, even if it's a toast explaining a demo limit.
- `esc()` everything rendered from state. No `innerHTML` with unescaped user input.
- Keep `filters.js` and `mail.js` DOM-free so they can move to the backend later unchanged.
