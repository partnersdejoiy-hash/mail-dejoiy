# Dejoiy Mail — Backend (Phase 1 MVP)

Multi-tenant mail-suite API. Node.js + Express + PostgreSQL + Redis.
Fully self-hosted: no external SaaS dependencies at runtime.

## Quick start

```bash
cp .env.example .env        # then edit passwords/keys
docker compose up -d        # postgres + redis
npm install
npm run db:migrate          # apply schema
npm run db:seed             # demo org "DEJOIY" + admin user
npm run dev                 # or: npm start
```

API base: `http://localhost:4000/api/v1` · Health: `GET /health`

Demo login (seed): `admin@workmail.dejoiy.com` — password from `SEED_ADMIN_PASSWORD`
(dev default `DejoiyDev123!`, printed with a warning by the seed script).

## Tests

```bash
npm test
```

Runs against in-memory Postgres (pg-mem) — no docker needed. Covers auth
(login/logout/RBAC/TOTP), mail (draft→send, folders, trash lifecycle, filters),
tenant isolation, seat enforcement, and domain onboarding.

## API overview (`/api/v1`)

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/2fa/setup|enable|disable` |
| Admin (admin+) | `GET/POST /admin/users`, `PATCH/DELETE /admin/users/:id` |
| Domains (admin+) | `GET/POST /admin/domains`, `GET /admin/domains/:id`, `POST /admin/domains/:id/check`, `POST /admin/domains/:id/verify` |
| Billing (admin+) | `GET /admin/billing`, `POST /admin/billing/seats`, `POST /admin/billing/subscribe` |
| Mail | `GET/POST/PATCH/DELETE /mail/folders`, `GET /mail/messages`, `GET/PATCH/DELETE /mail/messages/:id`, `POST/PATCH /mail/drafts`, `POST /mail/send`, `GET/POST/PATCH/DELETE /mail/filters` |
| Settings | `GET/PATCH /settings/profile`, `POST /settings/password`, `PATCH /settings/vacation` |

Auth: `Authorization: Bearer <token>`. Errors: `{ error: { code, message, details? } }`.

## Project layout

```
src/
  index.js            process entry (migrate → listen)
  app.js              express app factory (injectable pool, for tests)
  config.js           env-driven config
  db.js / redis.js    pg pool; redis client (optional, degrades gracefully)
  middleware/         auth (sessions+RBAC), rateLimit, validate (zod), errors
  routes/             auth, admin, mail, settings
  services/
    domains.js        required DNS records for customer onboarding
    mailer.js         outbox queue (stub provider — never claims delivery)
    billing.js        seat/subscription logic; Razorpay = clearly-marked STUB
  db/
    schema.sql        full multi-tenant schema (every table has org_id)
    migrate.js / seed.js
tests/                node:test + supertest + pg-mem
```

## Deliberately stubbed in this MVP (honest stubs, not silent fakes)

- **Outbound delivery** (`MAIL_PROVIDER=stub`): messages are persisted + queued in
  `outbox`, never sent. The API reports `delivered: false`. Real SMTP/SES wiring
  lands with the mail-server work (Pillar 1 of TECHNICAL_PLAN.md).
- **DNS verification** (`services/domains.js`): returns the *expected* records so the
  admin UI can display them; `check` is marked `stub: true` until real DNS lookups land.
- **Razorpay** (`services/billing.js`): seats/subscriptions work locally with an audit
  trail; every live-provider function throws `billing_not_live` until `BILLING_LIVE=true`
  with keys configured.
- **TOTP secret storage**: stored raw in MVP; column is named `totp_secret_enc` and the
  code carries a TODO to encrypt via KMS before production.

## Security notes

- Passwords: bcrypt (12 rounds). Sessions: 256-bit tokens, SHA-256 stored, expiry,
  revocation on logout/password-change/user-suspend.
- RBAC: `user < admin < super_admin`; self-demotion/self-suspend blocked.
- Tenant isolation enforced in every query by `org_id`; covered by tests.
- Rate limiting on all routes, stricter on `/auth/*`; Redis-backed when available.
