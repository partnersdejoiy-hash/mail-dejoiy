#!/usr/bin/env bash
# Dejoiy Mail backend deploy — SHARED BOX variant (dejoiy-desk, 178.104.228.157)
# Uses the server's EXISTING native postgres (127.0.0.1:5432) and redis
# (127.0.0.1:6379). Installs NOTHING system-wide except the app itself.
# Safe to re-run: skips steps that are already done.
set -euo pipefail

APP_DIR=/opt/dejoiy-mail/backend
REPO=https://github.com/partnersdejoiy-hash/mail-dejoiy.git
APP_PORT=4000
PG_USER=dejoiy_mail
PG_DB=dejoiy_mail

echo "--- 1. app code ---"
if [ -d "$APP_DIR/.git" ]; then
  echo "app dir already a git checkout, pulling"
  git -C "$APP_DIR" pull --ff-only || true
else
  rm -rf /opt/dejoiy-mail-tmp
  git clone --depth 1 --branch main "$REPO" /opt/dejoiy-mail-tmp
  mkdir -p "$APP_DIR"
  cp -r /opt/dejoiy-mail-tmp/backend/. "$APP_DIR"/
  rm -rf /opt/dejoiy-mail-tmp
fi
cd "$APP_DIR"
echo "--- 2. npm install ---"
npm ci --omit=dev --no-audit --no-fund

echo "--- 3. postgres role + database (native) ---"
if [ ! -f "$APP_DIR/.env" ]; then
  PG_PASS=$(openssl rand -hex 24)
  SEED_PASS=$(openssl rand -hex 12)
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$PG_USER') THEN
    CREATE ROLE $PG_USER LOGIN PASSWORD '$PG_PASS';
  ELSE
    ALTER ROLE $PG_USER WITH PASSWORD '$PG_PASS';
  END IF;
END
\$\$;
SELECT 'role ok';
EOF
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "SELECT 1 FROM pg_database WHERE datname = '$PG_DB'" -tA | grep -q 1 \
    || sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE $PG_DB OWNER $PG_USER"
  cat > "$APP_DIR/.env" <<EOF
NODE_ENV=production
PORT=$APP_PORT
DATABASE_URL=postgres://${PG_USER}:${PG_PASS}@127.0.0.1:5432/${PG_DB}
REDIS_URL=redis://127.0.0.1:6379
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
  chmod 600 "$APP_DIR/.env"
  echo "SAVED_NEW_ENV=1"
  echo "SEED_ADMIN_PASSWORD=${SEED_PASS}"
else
  echo ".env already exists, keeping it"
fi

echo "--- 4. migrate + seed ---"
set -a; . ./.env; set +a
npm run db:migrate
if [ "${SAVED_NEW_ENV:-}" = "1" ]; then
  npm run db:seed || echo "seed skipped/failed (may already be seeded)"
fi

echo "--- 5. systemd service ---"
cat > /etc/systemd/system/dejoiy-mail-api.service <<EOF
[Unit]
Description=Dejoiy Mail API
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=/usr/bin/node src/index.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now dejoiy-mail-api
sleep 4

echo "--- 6. health check ---"
if curl -sf "http://127.0.0.1:${APP_PORT}/health"; then
  echo ""
  echo "DEPLOY OK — API is running on 127.0.0.1:${APP_PORT}"
else
  echo ""
  echo "HEALTH CHECK FAILED — showing recent logs:"
  journalctl -u dejoiy-mail-api --no-pager -n 25
  exit 1
fi
