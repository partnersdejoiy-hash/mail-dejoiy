#!/usr/bin/env bash
# Connects Dejoiy Mail's Plan & billing page to Dejoiy Pay (pay.dejoiy.com). Run as root:
#   bash /opt/mail-dejoiy/deploy/connect-pay.sh
# Before running, in pay.dejoiy.com:
#   1. Developers > API keys: make a key (dp_test_… to try it out, dp_live_… for real money).
#   2. Developers > Webhooks: add https://mail.dejoiy.com/api/pay/webhook with the event payment.captured,
#      and copy its secret.
# The three values are read hidden and written only to the root-only env file; nothing is printed.
set -euo pipefail
DMAIL_ENV=${DMAIL_ENV:-/etc/dmail/adapter.env}

read -rp  "Dejoiy Pay key id (dp_test_… or dp_live_…): " KEY_ID
read -rsp "Dejoiy Pay key secret: " KEY_SECRET; echo
read -rsp "Webhook secret (Developers > Webhooks): " HOOK; echo
case "$KEY_ID" in dp_test_*|dp_live_*) ;; *) echo "The key id starts with dp_test_ or dp_live_."; exit 1;; esac
[ -n "$KEY_SECRET" ] && [ -n "$HOOK" ] || { echo "The key secret and the webhook secret are both needed."; exit 1; }

umask 077
sed -i '/^DEJOIY_PAY_KEY_ID=/d;/^DEJOIY_PAY_KEY_SECRET=/d;/^DEJOIY_PAY_WEBHOOK_SECRET=/d' "$DMAIL_ENV"
printf 'DEJOIY_PAY_KEY_ID=%s\nDEJOIY_PAY_KEY_SECRET=%s\nDEJOIY_PAY_WEBHOOK_SECRET=%s\n' "$KEY_ID" "$KEY_SECRET" "$HOOK" >> "$DMAIL_ENV"
unset KEY_SECRET HOOK

systemctl restart dmail
sleep 2
systemctl is-active --quiet dmail && echo "Dejoiy Mail restarted." || { echo "Dejoiy Mail did not start: journalctl -u dmail -n 30"; exit 1; }
case "$KEY_ID" in dp_test_*) echo "Test mode: payments on the billing page are simulated. Run this again with a dp_live_ key for real payments.";; esac
echo "Open the admin console > Manage > Plan & billing to see it."
