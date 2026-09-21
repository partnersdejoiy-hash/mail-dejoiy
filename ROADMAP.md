# Roadmap — from demo front-end to real mail product

## v0.1 — this repo ✅
Working front-end with local demo data. Every control functional.

## v0.2 — connect a real backend (the real work)
- Replace `js/data.js` with API calls (`GET /api/mail`, etc.).
- Auth: session login → replace the demo account menu.
- `Mail.send` → `POST /api/send` (outbound via Haraka/ZoneMTA).
- `Mail.checkMail` → IMAP IDLE / JMAP push (WildDuck).
- Filters: move `filters.js` logic server-side (Sieve or app-level), keep the same UI.
- Chat: WebSocket; Notes/Calendar/Contacts: per-user API storage.

## v0.3 — multi-tenancy + admin for real
- Organisations, custom domains, per-user seats (see the technical plan PDF).
- Admin panel calls real provisioning APIs (users, domains, DNS verification).
- Subscription/billing per user.

## The hard problems (not UI)
Email is a deliverability business: SPF/DKIM/DMARC, bounce + complaint handling,
abuse prevention, IP warm-up and reputation. Budget most engineering time here.
Reference: the 22-page Technical Plan (Sep 2026) — PWA-first, AWS SES as initial
outbound relay, WildDuck spike vs Stalwart.

## Cost discipline
Keep infra near-zero while pre-revenue: static front-end on free hosting
(GitHub Pages), single small VPS for the mail stack when real sending starts.
