#!/usr/bin/env bash
# One command to bring mail.dejoiy.com up to date (run as root on the server):
#   bash /opt/mail-dejoiy/deploy/update.sh
# Pulls the deploy branch, restarts the app, checks it, and switches on admin-mail.dejoiy.com
# once that name points at this server (nginx name + certificate). Safe to run again.
set -euo pipefail
BRANCH=fix/dejoiy-mail-completion
APP=/opt/mail-dejoiy
ADMIN_HOST=admin-mail.dejoiy.com

cd "$APP"
echo "== Updating code"
git pull --ff-only origin "$BRANCH"
git log --oneline -1

echo "== Restarting Dejoiy Mail"
systemctl restart dmail
for i in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8080/api/config >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8080/api/config && echo
systemctl is-active --quiet dmail && echo "dmail: running"

echo "== Admin site ($ADMIN_HOST)"
SERVER_IP=$(curl -fsS4 --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')
ADMIN_IP=$(getent ahostsv4 "$ADMIN_HOST" | awk 'NR==1{print $1}' || true)
if [ "$ADMIN_IP" != "$SERVER_IP" ]; then
  echo "Skipped: $ADMIN_HOST points to '${ADMIN_IP:-nothing}', this server is $SERVER_IP."
  echo "Add an A record: admin-mail -> $SERVER_IP, wait a few minutes, then run this script again."
else
  CONF=$(grep -l "server_name mail.dejoiy.com" /etc/nginx/sites-enabled/* | head -1)
  if ! grep -q "$ADMIN_HOST" "$CONF"; then
    cp "$CONF" "/root/$(basename "$CONF").bak.$(date +%s)"
    sed -i --follow-symlinks "s/server_name mail.dejoiy.com;/server_name mail.dejoiy.com $ADMIN_HOST;/" "$CONF"
  fi
  nginx -t && systemctl reload nginx
  if ! openssl x509 -in /etc/letsencrypt/live/mail.dejoiy.com/cert.pem -noout -text | grep -q "DNS:$ADMIN_HOST"; then
    certbot certonly --webroot -w /var/www/acme --cert-name mail.dejoiy.com -d mail.dejoiy.com -d "$ADMIN_HOST" \
      --expand --non-interactive --agree-tos --register-unsafely-without-email
    systemctl reload nginx
  fi
  curl -fsS -o /dev/null -w "https://$ADMIN_HOST -> %{http_code}\n" "https://$ADMIN_HOST/"
fi

echo "== Public check"
curl -fsS -o /dev/null -w "https://mail.dejoiy.com/home -> %{http_code}\n" https://mail.dejoiy.com/home
echo "Done. Open https://mail.dejoiy.com/home and press Ctrl+F5."
