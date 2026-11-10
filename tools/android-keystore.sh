#!/usr/bin/env bash
# Creates the Play upload key for both Android apps (needs Java's keytool), and prints what to paste
# into GitHub secrets and android-apps.json. Keep the .jks file and password safe and private.
set -euo pipefail
out="${1:-dejoiy-upload.jks}"
read -rsp "Choose a keystore password (6+ characters): " pass; echo
for alias in dejoiy-mail dejoiy-mail-admin; do
  keytool -genkeypair -v -keystore "$out" -storepass "$pass" -keypass "$pass" -alias "$alias" -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Dejoiy India Private Limited, O=Dejoiy India Private Limited, L=New Delhi, C=IN" >/dev/null 2>&1
done
echo; echo "1) GitHub secret DMAIL_KEYSTORE_PASSWORD: the password you just typed"
echo "2) GitHub secret DMAIL_UPLOAD_KEYSTORE_BASE64:"; base64 -w0 "$out" 2>/dev/null || base64 "$out"; echo
for alias in dejoiy-mail dejoiy-mail-admin; do
  echo "3) Upload key SHA-256 for $alias:"; keytool -list -v -keystore "$out" -storepass "$pass" -alias "$alias" | grep "SHA256:" | sed 's/.*SHA256: //'
done
