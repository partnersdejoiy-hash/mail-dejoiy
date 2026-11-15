#!/usr/bin/env bash
# Lets Dejoiy Mail sell and set up the Swiss Mail add-on (₹199 + GST a month, 10,000 mails).
# Run as root on the mail server:   bash /opt/mail-dejoiy/deploy/connect-swiss.sh
# Before running, on the Swiss Mail server put a long random PARTNER_SECRET in /opt/dejoiy-mail/deploy/env.prod
# and restart its API (see the reply that came with this script). Paste the same value here; it is read hidden,
# written only to the root-only env file, and never printed.
set -euo pipefail
DMAIL_ENV=${DMAIL_ENV:-/etc/dmail/adapter.env}
SWISS=${SWISS_URL:-https://api-mail.dejoiy.com}

read -rsp "Swiss Mail PARTNER_SECRET: " SECRET; echo
[ "${#SECRET}" -ge 32 ] || { echo "Use the long random value from the Swiss Mail server (at least 32 characters)."; exit 1; }

# does Swiss Mail accept it? (the header goes through a file so the secret never shows in the process list)
umask 077; H=$(mktemp); printf 'Authorization: Bearer %s\n' "$SECRET" > "$H"
code=$(curl -s -o /dev/null -w '%{http_code}' -H @"$H" "$SWISS/v1/partner/companies/check.invalid" || true); rm -f "$H"
case "$code" in
  404) echo "Swiss Mail accepted the secret." ;;
  401) echo "Swiss Mail did not accept it. Check PARTNER_SECRET on the Swiss Mail server and restart its API."; exit 1 ;;
  *)   echo "Swiss Mail answered $code. Is the new Swiss Mail API deployed at $SWISS?"; exit 1 ;;
esac

sed -i '/^SWISS_PARTNER_SECRET=/d;/^SWISS_URL=/d' "$DMAIL_ENV"
printf 'SWISS_PARTNER_SECRET=%s\nSWISS_URL=%s\n' "$SECRET" "$SWISS" >> "$DMAIL_ENV"
unset SECRET
systemctl restart dmail; sleep 2
systemctl is-active --quiet dmail && echo "Dejoiy Mail restarted. Admin → Domains → Mail service now offers Swiss Mail." \
  || { echo "Dejoiy Mail did not start: journalctl -u dmail -n 30"; exit 1; }
