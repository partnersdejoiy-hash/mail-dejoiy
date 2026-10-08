#!/bin/bash
set -euo pipefail
cert_dir=/etc/letsencrypt/live/mail.dejoiy.com
if [ -x /opt/zimbra/bin/zmcertmgr ]; then
  install -d -o zimbra -g zimbra -m 750 /opt/zimbra/ssl/acme
  install -o zimbra -g zimbra -m 640 "$cert_dir/privkey.pem" /opt/zimbra/ssl/zimbra/commercial/commercial.key
  install -o zimbra -g zimbra -m 644 "$cert_dir/cert.pem" /opt/zimbra/ssl/acme/cert.pem
  cat "$cert_dir/chain.pem" /etc/ssl/certs/ISRG_Root_X1.pem > /opt/zimbra/ssl/acme/chain.pem
  chown zimbra:zimbra /opt/zimbra/ssl/acme/chain.pem
  chmod 644 /opt/zimbra/ssl/acme/chain.pem
  runuser -l zimbra -c '/opt/zimbra/bin/zmcertmgr verifycrt comm /opt/zimbra/ssl/zimbra/commercial/commercial.key /opt/zimbra/ssl/acme/cert.pem /opt/zimbra/ssl/acme/chain.pem'
  runuser -l zimbra -c '/opt/zimbra/bin/zmcertmgr deploycrt comm /opt/zimbra/ssl/acme/cert.pem /opt/zimbra/ssl/acme/chain.pem'
  runuser -l zimbra -c '/opt/zimbra/bin/zmcontrol restart'
fi
nginx -t
systemctl reload nginx
