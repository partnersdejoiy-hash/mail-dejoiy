#!/usr/bin/env bash
# Dejoiy Mail — public HTTPS for the API (api.dejoiy.com).
#
# Run ON the server as root. Safe rules:
#   * Only ADDS a new nginx site for api.dejoiy.com; never edits existing sites.
#   * Stops (no changes) if port 80/443 is owned by something other than nginx.
#   * Never touches mail records, Shine, Postal, or other projects.
set -u

DOMAIN="api.dejoiy.com"
SERVER_IP="178.104.228.157"
APP_PORT="4001"

echo "--- 1. DNS propagation check ---"
IP=""
for i in $(seq 1 30); do
  IP=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1)
  if [ "$IP" = "$SERVER_IP" ]; then echo "DNS OK: $DOMAIN -> $IP"; break; fi
  echo "waiting for DNS ($i/30)... got: ${IP:-none}"
  sleep 20
done
[ "${IP:-}" = "$SERVER_IP" ] || { echo "DNS_NOT_READY: $DOMAIN does not resolve to $SERVER_IP yet. Wait and re-run."; exit 1; }

echo "--- 2. web server recon (read-only) ---"
ON80=$(ss -tlnp 2>/dev/null | grep -E ':80 ' || true)
ON443=$(ss -tlnp 2>/dev/null | grep -E ':443 ' || true)
echo "port80: ${ON80:-free}"
echo "port443: ${ON443:-free}"

if [ -n "$ON80" ] || [ -n "$ON443" ]; then
  if echo "$ON80 $ON443" | grep -qi caddy; then
    echo "STOP: Caddy owns port 80/443 here. Not touching its config — ask before proceeding."
    exit 2
  fi
  if ! echo "$ON80 $ON443" | grep -qi nginx; then
    echo "STOP: port 80/443 is owned by something that is not nginx. Not touching it — ask before proceeding."
    exit 2
  fi
  echo "nginx owns the web ports — will only ADD a new site file."
else
  echo "ports 80/443 are free — installing/enabling nginx."
  apt-get update -qq >/dev/null 2>&1
  apt-get install -y -qq nginx >/dev/null 2>&1 || { echo "nginx install failed"; exit 1; }
  systemctl enable --now nginx
fi

echo "--- 3. nginx site for $DOMAIN (port 80, certbot will add TLS) ---"
cat > /etc/nginx/sites-available/api.dejoiy.com <<EOF
server {
    listen 80;
    server_name api.dejoiy.com;
    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/api.dejoiy.com /etc/nginx/sites-enabled/api.dejoiy.com
nginx -t || { echo "nginx config test FAILED"; exit 1; }
systemctl reload nginx
echo "nginx site added + reloaded"

echo "--- 4. firewall (on-server only) ---"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80,443/tcp >/dev/null 2>&1
  echo "ufw: opened 80,443"
else
  echo "ufw not active — skipping (check Hetzner Cloud firewall allows 80/443 if certbot fails)"
fi

echo "--- 5. TLS certificate (Let's Encrypt) ---"
command -v certbot >/dev/null 2>&1 || apt-get install -y -qq certbot python3-certbot-nginx >/dev/null 2>&1 || { echo "certbot install failed"; exit 1; }
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || {
  echo "CERTBOT_FAILED: likely port 80 not reachable from outside (Hetzner Cloud firewall?) or DNS not fully propagated."
  exit 1
}
echo "certificate installed"

echo "--- 6. verify OUR api over https ---"
HEALTH_JSON=$(curl -sf "https://${DOMAIN}/health" || true)
if echo "$HEALTH_JSON" | grep -q '"ok":true'; then
  echo "$HEALTH_JSON"
  echo ""
  echo "HTTPS OK — Dejoiy Mail API is public at https://${DOMAIN}"
else
  echo "HTTPS check FAILED, got: $HEALTH_JSON"
  exit 1
fi
