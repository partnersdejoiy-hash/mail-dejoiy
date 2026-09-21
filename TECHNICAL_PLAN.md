# Dejoiy Mail — Real Mail Suite: Technical Plan
**Date:** 21 Sep 2026 · **Owner:** DEJOIY INDIA PRIVATE LIMITED
**Webmail:** dmail.dejoiy.com · **Company mail domain:** workmail.dejoiy.com

> Goal: multi-tenant mail suite. Companies add their own custom domains,
> per-user per-month billing, near-zero operating cost. Quality bar: Gmail /
> Zoho Mail / AOL Mail feature parity (surveys completed Sep 2026).

---

## Pillar 1 — Mail infrastructure (sabse critical)

**Phase 1 (MVP):**
- 1 VPS (Hetzner CX22 ≈ ₹450/month): Postfix (SMTP) + Dovecot (IMAP) + Rspamd (spam filter).
- Outbound via AWS SES smart relay (≈ ₹9 per 10,000 mails) until our IPs are warmed.
- Inbound MX for `workmail.dejoiy.com` → our VPS from day one (low volume = safe learning ground).

**Deliverability (non-negotiable):**
- Per-domain DNS: MX, SPF (`v=spf1`), DKIM (per-domain keypair, selector `dmail`), DMARC (`p=none` → `quarantine` → `reject` over weeks).
- IP warmup: ramp sending volume over 4–8 weeks; separate IPs for transactional vs bulk later.
- Postmaster tools: register with Google, Yahoo, Outlook; feedback loops; automatic bounce/complaint suppression list.
- Blacklist monitoring (Spamhaus etc.) with alerts.

**Phase 2:** dedicated IPs, multiple VPS regions, outbound IP pools per tenant tier.

## Pillar 2 — Backend

- **Stack:** Node.js + PostgreSQL + Redis (largest hiring pool in India, cheapest to run solo).
- **Multi-tenancy:** orgs → domains → users; every row scoped by `org_id`.
- **Auth:** sessions + optional 2FA; role model (Super Admin / Admin / User) mirroring Zoho's, which the team already knows.
- **Billing:** Razorpay subscriptions; per-seat per-month; seat add/remove proration; dunning for failed payments.
- **Storage:** Maildir on VPS → S3-compatible object storage for attachments as volume grows.
- **APIs (REST):** auth, messages (list/read/send/draft), folders/labels, filters, contacts, calendar, admin (users/domains/billing), settings — the webmail UI binds to these.

## Pillar 3 — Frontend

- Current build is the design reference (24 themes, Today, 3D, responsive phone/tablet/desktop).
- Production rebuild (React recommended for hiring) at **dmail.dejoiy.com**, API-driven, no demo data.
- Phone/tablet layouts already specified: same features, adaptive layout only.

## Pillar 4 — Ops & business

- Daily encrypted offsite backups; uptime + mail-queue + blacklist monitoring with alerts.
- Abuse control: per-user rate limits, spam-complaint auto-suspend, outbound content scanning.
- Pricing sketch: ₹99–149/user/month starter (undercuts Zoho/Google, keeps margin at our cost base).
- Support: in-app ticket flow; onboarding checklist per company.

---

## Custom-domain onboarding (for other companies)

Two supported paths — customer picks one:

**Option A — DNS records (recommended, lowest friction):**
Customer adds 5 records at their registrar/DNS:
1. `MX` → `mail.dmail.dejoiy.com`
2. `TXT` SPF: `v=spf1 include:mail.dmail.dejoiy.com ~all`
3. `TXT` DKIM: `dmail._domainkey` → (key we generate per domain)
4. `TXT` DMARC: `_dmarc` → `v=DMARC1; p=none; rua=mailto:dmarc@dejoiy.com`
5. Optional `CNAME` webmail → `dmail.dejoiy.com` (white-label login)
We auto-verify via DNS polling (like Zoho does), then provision mailboxes.

**Option B — Our nameservers:**
Customer sets `ns1.dmail.dejoiy.com` / `ns2.dmail.dejoiy.com` at their registrar;
we host their zone on PowerDNS + API and create all mail records automatically.
Zero manual work for them; bigger trust ask.

---

## Dejoiy's own setup (immediate, zero-risk)

Current `dejoiy.com` mail runs on Zoho (5 users) — **its MX records will NOT be touched.**

| Record | Value | Risk |
|---|---|---|
| `dmail.dejoiy.com` CNAME | webmail host (now GitHub Pages; later app VPS) | None (new) |
| `workmail.dejoiy.com` MX | our VPS (Phase 1) | None (new subdomain) |
| `workmail.dejoiy.com` TXT/SPF/DKIM/DMARC | per Pillar 1 | None (new) |
| `dejoiy.com` SPF fix | correct Zoho include, remove broken entry | Safe (TXT only, inbound unaffected) |
| `dejoiy.com` DMARC | `p=none` monitoring | Safe |

## Cost & timeline (honest)

- **Now:** ₹0 (DNS audit + fixes + CNAME).
- **Phase 1 MVP (4–6 weeks):** VPS ₹450/mo + SES usage-based → **< ₹1,000/month** at pilot scale.
- **Full production suite:** 8–12 weeks at solo-with-AI pace, built in thin tested slices.
- Revenue starts at first paying company; break-even ≈ 10–15 paid seats.
