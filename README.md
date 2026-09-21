# mail-dejoiy — Dejoiy Mail

**Dejoiy Mail** (short: **D-mail**) — a fast, beautiful, multi-tenant webmail app for companies:
custom domains, per-user pricing, and a best-in-class interface with 24 themes.

> **Status (v0.1):** This repo currently holds the **complete, working front-end source code**
> (`web/`). It runs with zero dependencies and zero build step — open `web/index.html`
> or serve the folder with any static server. The demo mailbox runs locally in the
> browser (localStorage); the real mail backend (SMTP/IMAP, deliverability, multi-tenancy)
> is tracked in `docs/ROADMAP.md`.

## Quick start

```bash
cd web
python3 -m http.server 8080
# open http://localhost:8080
```

No build, no npm, no bundler. Just HTML + CSS + vanilla JS.

## What's inside

| Path | What it is |
|---|---|
| `web/index.html` | App shell (header, sidebar, views, dialogs, toasts) |
| `web/css/` | `base` (tokens), `themes` (24 themes + light/medium/dark), `layout` (desktop/tablet/phone), `components` |
| `web/js/data.js` | Demo mailbox content — **replace with API calls** when the backend lands |
| `web/js/store.js` | State + localStorage persistence |
| `web/js/themes.js` | Theme engine: 24 themes, independent brightness, custom photo upload |
| `web/js/filters.js` | Gmail-style filter engine (criteria → actions), actually runs |
| `web/js/mail.js` | Mailbox operations: send, reply, move, star, search, simulated fetch |
| `web/js/view-*.js` | Views: Today, Mail (3-pane + tabs), Compose (rich text), Calendar, Contacts (CSV), Notes, Chat, Admin, Settings |
| `web/js/app.js` | Router, dialogs, menus, keyboard shortcuts, sounds |
| `docs/` | Architecture, roadmap, theme guide |

## Features (v0.1)

- 📥 Mail: folders, smart views, message tabs, starring, labels, archive/spam/trash
- ✎ Compose: rich text, Cc, attachments, drafts, reply / reply-all / forward
- 🎨 **24 themes** (13 colour + 11 scenic) + light/medium/dark + your own photo — instant apply
- 📰 Today dashboard with headlines, schedule and to-dos
- 🧹 **Working filters**: from/to/subject/words/size/date/attachment → archive, star, label, forward, delete, never-spam…
- 🔎 Advanced search with “create filter from this search”
- 📅 Calendar + to-dos, 👥 Contacts with CSV import/export, 📝 Notepad, 💬 Chat, 🛡️ Admin (users, domains, DNS toggles)
- ⌨️ Full keyboard shortcuts (press `?`), 🔊 sounds, 📱 responsive phone/tablet/desktop layouts

## The real backend

The hard part of a mail product is deliverability (SPF/DKIM/DMARC, bounces, IP reputation)
and multi-tenancy — not the UI. See `docs/ROADMAP.md` for the backend plan
(WildDuck/Haraka/ZoneMTA + Rspamd, per the technical plan) and how `web/` plugs into it.
