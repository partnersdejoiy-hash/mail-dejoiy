# Dejoiy Mail backend — Hetzner deploy runbook

**Server:** dejoiy-desk (Hetzner Cloud CPX22, Nuremberg) — `178.104.228.157`
**Date prepared:** 21 Sep 2026
**Status:** waiting on SSH access (Roopa to add deploy public key to /root/.ssh/authorized_keys)

## Preconditions
- [ ] SSH as root works: `ssh root@178.104.228.157`
- [ ] DNS: `api.dejoiy.com` A record → `178.104.228.157` (needs Zoho DNS access — Roopa approval required before any DNS edit; present exact effect + rollback first)
- [ ] Existing services on the server audited (deploy.sh does this first and aborts on surprises)

## Architecture on the server
- Node.js 20 (NodeSource) running the API via systemd: `dejoiy-mail-api`
- PostgreSQL 16 + Redis 7 via Docker Compose (matches repo `backend/docker-compose.yml`)
- Nginx reverse proxy → `https://api.dejoiy.com` (Let's Encrypt via certbot), proxies to `127.0.0.1:4000`
- App code at `/opt/dejoiy-mail/backend` (git clone of `partnersdejoiy-hash/mail-dejoiy`, `backend/` subdir)
- `.env` generated on the server with random secrets — never committed

## Steps (once SSH works)
1. `scp docs/deploy/deploy.sh root@178.104.228.157:/root/deploy.sh`
2. `ssh root@178.104.228.157 'bash /root/deploy.sh --audit-only'` — review audit output
3. After Roopa approves DNS: create `api.dejoiy.com` A → `178.104.228.157` in Zoho DNS
4. `ssh root@178.104.228.157 'bash /root/deploy.sh'`
5. Verify: `curl https://api.dejoiy.com/health` should return `{"ok":true,...}`
6. Update live frontend `DMAIL_API_BASE` to `https://api.dejoiy.com/api/v1`, republish gh-pages
7. Real-browser QA: login → Connected mode on dmail.dejoiy.com

## Do NOT
- Touch MX/SPF/DKIM/DMARC (SPF work is paused by Roopa)
- Break existing services on dejoiy-desk (it already sends mail for dejoiy.com per SPF `ip4:178.104.228.157`)
- Expose Postgres/Redis publicly (bind 127.0.0.1 only)
- Commit `.env` or any secret to git
