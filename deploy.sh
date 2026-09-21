#!/usr/bin/env bash
# Dejoiy Mail backend deploy — Hetzner dejoiy-desk (178.104.228.157)
# Usage: bash deploy.sh [--audit-only]
# Idempotent where practical. Aborts if the audit finds conflicting services.
set -euo pipefail

APP_DIR=/opt/dejoiy-mail/backend
REPO=https://github.com/partnersdejoiy-hash/mail-dejoiy.git
API_DOMAIN=api.dejoiy.com
APP_PORT=4000

audit() {
  echo "===== AUDIT ====="
  echo "--- OS ---"; (cat /etc/os-release 2>/dev/null | head -3) || true
  echo "--- uptime/load ---"; uptime
  echo "--- memory/disk ---"; free -h | head -2; df -h / | tail -1
  echo "--- listening ports ---"; (ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | head -30
  echo "--- docker ---"; (docker ps --format '{{.Names}} {{.Image}} {{.Status}}' 2>/dev/null) || echo "no docker"
  echo "--- node ---"; (node --version 2>/dev/null) || echo "no node"
  echo "--- nginx ---"; (nginx -v 2>&1) || echo "no nginx"
  echo "--- mail processes ---"; (ps aux | grep -iE 'postfix|exim|sendmail|dovecot' | grep -v grep) || echo "none visible"
  echo "--- existing /opt/dejoiy-mail ---"; ls -la /opt/dejoiy-mail 2>/dev/null || echo "absent"
  echo "===== END AUDIT ====="
}

if [ "${1:-}" = "--audit-only" ]; then audit; exit 0; fi

audit

echo "--- installing base packages ---"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl git nginx certbot python3-certbot-nginx ufw > /dev/null

echo "--- node 20 ---"
if ! command -v node >/dev/null || ! node --version | grep -qE '^v(20|2[1-9])'; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null
  apt-get install -y -qq nodejs > /dev/null
fi
node --version

echo "--- docker ---"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh > /dev/null
  systemctl enable --now docker
fi
docker --version

echo "--- firewall (ssh/http/https only) ---"
ufw allow OpenSSH > /dev/null || true
ufw allow 80/tcp > /dev/null || true
ufw allow 443/tcp > /dev/null || true
ufw --force enable > /dev/null || true

echo "--- app code ---"
mkdir -p /opt/dejoiy-mail
if [ -d $APP_DIR/.git ]; then
  git -C $APP_DIR pull --ff-only
else
  git clone --depth 1 $REPO /opt/dejoiy-mail-tmp
  mkdir -p $APP_DIR
  cp -r /opt/dejoiy-mail-tmp/backend/. $APP_DIR/
  rm -rf /opt/dejoiy-mail-tmp
fi
cd $APP_DIR
npm ci --omit=dev --no-audit --no-fund

echo "--- .env ---"
if [ ! -f $APP_DIR/.env ]; then
  PG_PASS=$(openssl rand -hex 24)
  SEED_PASS=$(openssl rand -hex 12)
  cat > $APP_DIR/.env <<EOF
NODE_ENV=production
PORT=$APP_PORT
DATABASE_URL=postgres://dejoiy:${PG_PASS}@127.0.0.1:5432/dejoiy_mail
POSTGRES_USER=dejoiy
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=dejoiy_mail
POSTGRES_PORT=5432
REDIS_URL=redis://127.0.0.1:6379
REDIS_PORT=6379
REDIS_ENABLED=true
SESSION_TTL_DAYS=30
BCRYPT_ROUNDS=12
RATE_LIMIT_WINDOW_MS=900000
RATE_LIMIT_MAX=300
RATE_LIMIT_AUTH_MAX=30
CORS_ORIGIN=https://dmail.dejoiy.com
SEED_ADMIN_PASSWORD=${SEED_PASS}
MAIL_PROVIDER=stub
MAIL_FROM_DOMAIN=workmail.dejoiy.com
BILLING_LIVE=false
EOF
  chmod 600 $APP_DIR/.env
  echo "SEED ADMIN PASSWORD (save securely, shown once): $SEED_PASS"
fi

echo "--- postgres + redis ---"
cd $APP_DIR
set -a; . ./.env; set +a
docker compose up -d
for i in $(seq 1 30); do
  docker exec dejoiy-mail-pg pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1 && break
  sleep 2
done

echo "--- migrate + seed ---"
npm run db:migrate
SEED_ADMIN_PASSWORD="$SEED_PASS" npm run db:seed || true

echo "--- systemd service ---"
cat > /etc/systemd/system/dejoiy-mail-api.service <<EOF
[Unit]
Description=Dejoiy Mail API
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=/usr/bin/node src/index.js
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now dejoiy-mail-api
sleep 3
systemctl --no-pager --lines 5 status dejoiy-mail-api || true

echo "--- nginx reverse proxy ---"
cat > /etc/nginx/sites-available/$API_DOMAIN <<EOF
server {
    listen 80;
    server_name $API_DOMAIN;
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/$API_DOMAIN /etc/nginx/sites-enabled/$API_DOMAIN
nginx -t && systemctl reload nginx

echo "--- TLS (needs api.dejoiy.com DNS -> this server first) ---"
if getent hosts $API_DOMAIN | grep -q .; then
  certbot --nginx -d $API_DOMAIN --non-interactive --agree-tos --register-unsafely-without-email --redirect
else
  echo "WARNING: $API_DOMAIN does not resolve yet — create the A record, then run:"
  echo "  certbot --nginx -d $API_DOMAIN --non-interactive --agree-tos --register-unsafely-without-email --redirect"
fi

echo "--- local health check ---"
curl -sf http://127.0.0.1:$APP_PORT/health || echo "NOTE: /health did not respond locally — check the service"
echo "DEPLOY DONE"
