#!/usr/bin/env bash
# Connects Dejoiy Mail's Plan & billing page, and Shine-on-its-own billing, to Dejoiy Pay (pay.dejoiy.com).
# Run as root:   bash /opt/mail-dejoiy/deploy/connect-pay.sh
# Before running, in pay.dejoiy.com (same mode as the key: Test for dp_test_, Live for dp_live_):
#   1. Developers > API keys: make a key.
#   2. Developers > Webhooks: add https://mail.dejoiy.com/api/pay/webhook (event payment.captured) and copy its secret.
#   3. Optional, for Shine on its own: add https://convex-site.shine.dejoiy.com/dejoiy-pay/webhook too and copy its secret
#      (without it Shine still sees payments, from its billing page).
# Values are read hidden and written only to root-only env files; nothing is printed.
set -euo pipefail
DMAIL_ENV=${DMAIL_ENV:-/etc/dmail/adapter.env}
SHINE_DIR=${SHINE_DIR:-/opt/shine}

read -rp  "Dejoiy Pay key id (dp_test_… or dp_live_…): " KEY_ID
read -rsp "Dejoiy Pay key secret: " KEY_SECRET; echo
read -rsp "Webhook secret for mail.dejoiy.com: " HOOK; echo
read -rsp "Webhook secret for Shine (Enter to skip): " SHINE_HOOK; echo
case "$KEY_ID" in dp_test_*|dp_live_*) ;; *) echo "The key id starts with dp_test_ or dp_live_."; exit 1;; esac
[ -n "$KEY_SECRET" ] && [ -n "$HOOK" ] || { echo "The key secret and the mail webhook secret are both needed."; exit 1; }

umask 077
sed -i '/^DEJOIY_PAY_KEY_ID=/d;/^DEJOIY_PAY_KEY_SECRET=/d;/^DEJOIY_PAY_WEBHOOK_SECRET=/d' "$DMAIL_ENV"
printf 'DEJOIY_PAY_KEY_ID=%s\nDEJOIY_PAY_KEY_SECRET=%s\nDEJOIY_PAY_WEBHOOK_SECRET=%s\n' "$KEY_ID" "$KEY_SECRET" "$HOOK" >> "$DMAIL_ENV"
if [ -d /etc/shine ]; then
  printf 'DEJOIY_PAY_KEY_ID=%s\nDEJOIY_PAY_KEY_SECRET=%s\n' "$KEY_ID" "$KEY_SECRET" > /etc/shine/pay.env
  [ -n "$SHINE_HOOK" ] && printf 'DEJOIY_PAY_WEBHOOK_SECRET=%s\n' "$SHINE_HOOK" >> /etc/shine/pay.env
fi
unset KEY_SECRET HOOK SHINE_HOOK

systemctl restart dmail
sleep 2
systemctl is-active --quiet dmail && echo "Dejoiy Mail restarted." || { echo "Dejoiy Mail did not start: journalctl -u dmail -n 30"; exit 1; }
if [ -f /etc/shine/pay.env ] && [ -f "$SHINE_DIR/deploy/contabo/update.sh" ]; then
  echo "== Shine (pushes the payment settings to Shine's backend)"
  FIRST=1 bash "$SHINE_DIR/deploy/contabo/update.sh"
fi
case "$KEY_ID" in dp_test_*) echo "Test mode: payments are simulated. Run this again with a dp_live_ key for real payments.";; esac
echo "Open the admin console > Manage > Plan & billing to see it."
