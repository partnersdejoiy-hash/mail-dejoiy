#!/usr/bin/env bash
# Switches on companies' own sign-in addresses (mail.theircompany.com) for Dejoiy Mail. Run as root;
# update.sh installs it to run every 10 minutes:  bash /opt/mail-dejoiy/deploy/custom-hosts.sh
# The app writes the verified addresses to LIST (admins add them in the Admin console → Domains).
# Each address gets its own certificate and its own nginx file; a bad one never breaks the main site.
set -uo pipefail
LIST=${CUSTOM_HOSTS_FILE:-/var/lib/dmail/custom-hosts.txt}
APP=${APP_UPSTREAM:-http://127.0.0.1:8080}
ACME=/var/www/acme
DIR=/etc/nginx/conf.d
[ -f "$LIST" ] || exit 0
SERVER_IP=$(curl -fsS4 --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')
changed=0; keep=" "
while IFS= read -r host; do
  # only plain host names ever reach nginx or certbot
  [[ "$host" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.){2,}[a-z]{2,63}$ ]] || continue
  keep="$keep$host "
  conf="$DIR/dmail-custom-$host.conf"
  [ -f "$conf" ] && [ -f "/etc/letsencrypt/live/$host/fullchain.pem" ] && continue
  [ "$(getent ahostsv4 "$host" | awk 'NR==1{print $1}')" = "$SERVER_IP" ] || { echo "$host: not pointing here yet"; continue; }
  # step 1: plain HTTP, so the certificate check can reach us
  cat > "$conf" <<NGINX
server { listen 80; listen [::]:80; server_name $host;
  location /.well-known/acme-challenge/ { root $ACME; }
  location / { return 301 https://\$host\$request_uri; } }
NGINX
  nginx -t 2>/dev/null && systemctl reload nginx || { rm -f "$conf"; echo "$host: nginx refused the file"; continue; }
  certbot certonly --webroot -w "$ACME" -d "$host" --non-interactive --agree-tos --register-unsafely-without-email --quiet \
    || { echo "$host: certificate not issued yet (will retry)"; continue; }
  # step 2: HTTPS, passed to the mail app with the address the person typed
  cat >> "$conf" <<NGINX
server { listen 443 ssl; listen [::]:443 ssl; server_name $host;
  ssl_certificate /etc/letsencrypt/live/$host/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/$host/privkey.pem;
  add_header Strict-Transport-Security "max-age=31536000" always;
  client_max_body_size 22m;
  location / { proxy_pass $APP; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$remote_addr; proxy_set_header X-Forwarded-Proto https; proxy_read_timeout 120s; } }
NGINX
  if nginx -t 2>/dev/null; then changed=1; echo "$host: live"; else sed -i '/listen 443/,$d' "$conf"; echo "$host: HTTPS file refused, kept HTTP only"; fi
done < "$LIST"
# addresses an admin removed: take their nginx file away (the certificate just expires)
for conf in "$DIR"/dmail-custom-*.conf; do
  [ -e "$conf" ] || continue
  host=${conf##*/dmail-custom-}; host=${host%.conf}
  case "$keep" in *" $host "*) ;; *) rm -f "$conf"; changed=1; echo "$host: removed";; esac
done
[ "$changed" = 1 ] && nginx -t 2>/dev/null && systemctl reload nginx
exit 0
