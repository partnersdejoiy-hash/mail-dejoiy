# Contabo Dmail deployment

Installed on 2026-10-08. Real local mail and browser acceptance passed. External send/receive and public DKIM/DMARC validation remain pending; do not claim full delivery acceptance.

Host: Ubuntu 24.04 x86_64, `mail.dejoiy.com`, `173.249.23.93`.
Mail domain: `corp.dejoiy.com`. Root-domain Zoho MX records are preserved.
The customer interface is the existing `web/` Dmail app; stock Zimbra webmail is not published.

## Build and backups

Pinned official `Zimbra/zm-build` tag `10.1.21`, commit `f40c9007407061e74d48cc19a208b0cbfb9685ec`.
Builder image: `dejoiy-zimbra-builder:ubuntu24`, built from official `zm-base-os/Dockerfile-devcore-ubuntu-24.04`.
Container: `dejoiy-zimbra-source-build`; no production services run in that container.
Persistent build session: `zimbra-source-build`. Launch script: `/opt/zimbra-build/operations/build.sh`.
Build log: `/opt/zimbra-build/zimbra-build.log`; builder image log: `/opt/zimbra-build/builder-image.log`.
Sources and artifacts: `/opt/zimbra-build/work/`, resulting archive at `work/.staging/UBUNTU24_64-DAFFODIL-10121-20261008025547-FOSS-1000/zm-build/zcs-10.1.21_GA_1000.UBUNTU24_64.20261008025547.tgz`.
Actual installed version: `10.1.21.GA.1000.UBUNTU24.64`, FOSS edition (verified with `zmcontrol -v`).

Descending component tag fallback follows upstream's method; build release is `DAFFODIL`, type is `FOSS`.
Third-party build dependencies come from upstream repositories and `files.zimbra.com`.

Initial private backup: `/opt/zimbra-build/backups/initial/etc.tgz` and `dns.json`.
Before changing configuration again, take a new root-only backup. Do not blindly restore all of `/etc` on a running server.

## Dmail HTTPS and service

Repository: `/opt/mail-dejoiy`, branch `feat/zimbra-10.1-integration`.
URL: `https://mail.dejoiy.com`. nginx owns ports 80/443.
Service: `dmail.service`, user `dmail`, loopback listener `127.0.0.1:8080`.
Configuration: `/etc/dmail/adapter.env` (0600). Sessions: `/var/lib/dmail/sessions.sqlite` (0600, directory 0700).
Session storage contains upstream auth tokens. Protect it and its backups as secrets.
Sessions persist across adapter restarts. nginx overwrites X-Real-IP, and the loopback adapter trusts that header only from a loopback peer; login limits therefore apply per client IP.
No admin credential is passed to the adapter. HTTPS certificate validation remains enabled.

```bash
systemctl status dmail nginx
journalctl -u dmail --since today
nginx -t
systemctl restart dmail
systemctl reload nginx
curl --fail https://mail.dejoiy.com/api/config
```

Deployment templates are in `deploy/`. Runtime configuration enables live mode; static hosting alone remains demo mode and must not replace this service.

Certificate: `/etc/letsencrypt/live/mail.dejoiy.com/`, managed by `certbot.timer`.
Issued using:

```bash
certbot certonly --webroot -w /var/www/acme -d mail.dejoiy.com --non-interactive --agree-tos --register-unsafely-without-email
```

Deploy certificate to Zimbra using `deploy/renew-zimbra-certificate.sh` only after Zimbra is configured.
The script verifies the chain, installs the certificate, restarts Zimbra and reloads nginx.
Private keys are never in this repository. `/opt/zimbra-build/operations/prepare-setup.py` redacts setup logging before credential provisioning.

## Firewall, hostname and DNS

UFW allows TCP 22, 25, 80, 443, 465, 587 and 993. Other inbound ports, including 389, 636, 7071, 7306 and adapter ports, are blocked.
SSH was preserved. Do not publish container ports or add broad firewall exceptions.
`/etc/hosts` maps the public IP to `mail.dejoiy.com mail`.
`/etc/cloud/cloud.cfg.d/99-zimbra-hostname.cfg` preserves hostname and disables hosts rewriting.
`systemd-timesyncd` synchronizes the clock.

Verified A/PTR and corp MX point to this host. Root MX: `mx.zoho.in`, `mx2.zoho.in`, `mx3.zoho.in`.
Existing corp SPF: `v=spf1 mx ip4:217.216.79.163 ~all`.
Proposed replacement, preserving the previously authorized IP: `v=spf1 mx ip4:173.249.23.93 ip4:217.216.79.163 ~all`.
Replace the existing SPF record; never add a second SPF TXT record.
Old selector from DNS snapshot: `b4960fdc-2e70-11f1-8476-056c747b400a`. No matching private key exists on this installation; do not reuse it.
The installation uses new selector `dmail20261008`. Exact new DKIM, replacement SPF and corporate DMARC are in [CORP-DNS.txt](CORP-DNS.txt), also available at `https://mail.dejoiy.com/dns-records.txt`. Public DNS publication is pending. Do not change root-domain DNS.

## Credentials and recovery

Generated credentials are kept in `/etc/dmail/credentials.json` (root only). The active test mailbox is `test@corp.dejoiy.com`; the administrator is `admin@corp.dejoiy.com`.
Retrieve over a trusted administrative SSH session with `sudo cat /etc/dmail/credentials.json`; do not paste the contents into tickets, chat, logs or Git.
Installation defaults with secrets: `/etc/dmail/zimbra-install.conf` (0600).

For adapter failures inspect `journalctl -u dmail`, nginx `/var/log/nginx/error.log`, then test the internal SOAP endpoint's certificate.
For mail failures inspect `/var/log/zimbra.log`, `/opt/zimbra/log/mailbox.log` and `su - zimbra -c 'zmcontrol status'`.
Do not rerun the installer against an existing mailbox installation without reviewing state and taking a consistent backup.
The initial `/etc` archive does not back up mailboxes. Add and test a separate consistent Zimbra mail/LDAP backup before business use.

## Feature limits

Latest 50 messages only; search, counts and Empty Trash operate on that loaded window. Text-only send/render. Attachments cannot be uploaded or downloaded.
Custom folders, server labels/filters, contacts, calendar, chat, notes, account settings, quotas, provisioning and billing are not connected.
Appearance preferences persist separately in browser storage; message data and tokens never enter browser storage. Appearance and shortcuts remain accessible. Admin demo screens are blocked. Node stub delivery is not used.

## Exact installation and repairs

The installer archive checksum is recorded in `/opt/zimbra-build/operations/installer.sha256`. The build exited 0.

```bash
tar -xzf /opt/zimbra-build/work/.staging/UBUNTU24_64-DAFFODIL-10121-20261008025547-FOSS-1000/zm-build/zcs-10.1.21_GA_1000.UBUNTU24_64.20261008025547.tgz -C /opt/zimbra-build/installer
cd /opt/zimbra-build/installer/zcs-10.1.21_GA_1000.UBUNTU24_64.20261008025547
./install.sh -s /etc/dmail/zimbra-install.conf
python3 /opt/zimbra-build/operations/prepare-setup.py
/opt/zimbra/libexec/zmsetup.pl -c /etc/dmail/zimbra-install.conf
```

Do not regenerate or print existing secrets when recovering. The private defaults file is maintained on the server and is deliberately not committed.
Initial APT validation failed because the installer created `/etc/apt/trusted.gpg.d/zimbra.gpg` as 0600. Corrected with `chmod 644 /etc/apt/trusted.gpg.d/zimbra.gpg`; `apt-get update` then validated all official repositories. Signing subkey fingerprint: `E4702EEBFF806710EB4124825234D2B73B6996C7`.

Setup computes spam/ham/quarantine addresses before loading the requested domain. The initial addresses at `mail.dejoiy.com` failed because only the corporate domain exists. `/opt/zimbra-build/operations/postconfigure.py` creates `spam.training`, `ham.training` and `virus-quarantine` under `corp.dejoiy.com` and sets the respective global attributes. Private defaults now include those correct addresses.

Backend HTTP/HTTPS ports: 8081/8443; SOAP target in adapter environment: `https://mail.dejoiy.com:8443`. Zimbra HTTP proxy is disabled. nginx owns the public interface. memcached binds `127.0.0.1:11211`; its client list uses that address. SMTP enforces TLS for authenticated submission; outbound SMTP uses opportunistic TLS. Internal certificate exceptions were disabled after deployment:

```bash
su - zimbra -c 'zmlocalconfig -e ssl_allow_untrusted_certs=false ssl_allow_mismatched_certs=false'
systemctl enable zimbra
systemctl restart zimbra
```

The admin WAR and timezone data were restored from the locally built `zimbra-mbox-admin-console-war` and `zimbra-timezone-data` packages after disabling customer webapps removed their assets. Admin service is enabled; customer Zimbra webmail is not enabled. Administration URL is `https://mail.dejoiy.com:7071/zimbraAdmin/`, reachable only through an administrative tunnel/private route. Public 7071 is blocked. For a tunnel, use `ssh -L 7071:127.0.0.1:7071 root@173.249.23.93` and a local name mapping for `mail.dejoiy.com` to preserve certificate hostname validation. Never open 7071 publicly as a workaround.

This source build omits the Log4j 1 compatibility API although spymemcached explicitly chooses its Log4j 1 logger. Startup reports `NoClassDefFoundError: org/apache/log4j/Priority`. `deploy/install-log4j-bridge.py` installs Apache's `log4j-1.2-api:2.17.1`, matching the build's Log4j 2 API/core, from Maven Central over HTTPS with a published artifact checksum check. It preserves the licence and NOTICE embedded in the JAR. Reapply after an upgrade if the new build still needs it; do not install the obsolete Log4j 1 backend. Source: https://logging.apache.org/log4j/2.x/migrate-from-log4j1.html.

Certificate deployment command: `/opt/zimbra-build/operations/deploy-certificate.sh`. Renewal hook: `/etc/letsencrypt/renewal-hooks/deploy/dmail-zimbra`. It concatenates the full issued intermediate chain and the trusted ISRG Root X1; verification passed for the actual issued chain. `certbot.timer` is enabled. Use `certbot renew --dry-run` to validate the ACME renewal path; the deploy hook is not run by default during dry-run.

Logs: `operations/zimbra-install.log`, `operations/zimbra-setup.log`, `/opt/zimbra/log/zmsetup.20261008-051928.log`, `operations/certificate-deploy.log`, `operations/postconfigure.log`, `operations/restart-verified.log`, `operations/restart-bridge.log`, `/var/log/zimbra.log`, `/opt/zimbra/log/mailbox.log`, `/opt/zimbra/log/zmmailboxd.out`, and `journalctl -u dmail -u zimbra -u nginx`. Operational directory prefix is `/opt/zimbra-build/`. Setup logging redaction must be reapplied if its script is replaced.

## Verified acceptance and remaining work

- Python adapter: 11 tests; JavaScript adapter: 4 tests.
- Real Zimbra login, secure cookie, inbox retrieval, self-delivery via SOAP and local SMTP ingress.
- Correct sender and return path at `test@corp.dejoiy.com`; received messages contain DKIM `d=corp.dejoiy.com; s=dmail20261008`.
- Read, star, importance, move to Archive/back, draft save/edit and logout.
- Adapter sessions survive restart. All installed Zimbra services returned Running after a full service restart; tests repeated afterwards.
- Headless browser: Dmail login/inbox, composing and sending a real message, appearance/shortcut settings, no page errors, no mail data in localStorage.
- Trusted TLS authentication: SMTP 587 with STARTTLS, SMTP 465, IMAP 993.
- Probe from an untrusted Docker network: public 25/443/993 reachable; LDAP 389, admin 7071, database 7306, SOAP 8443, adapter 8080 and memcached 11211 blocked. Unauthenticated relay RCPT rejected with SMTP 554; no DATA was sent.
- Public corporate DNS records and external delivery are NOT yet accepted. Obtain an explicitly approved recipient before sending any external test. Send from the Dmail UI, receive a reply, inspect both sides' authentication headers, and confirm SPF/DKIM/DMARC results before business launch.

Evidence on the server: `operations/acceptance-results.json`, `operations/browser-results.json`, `operations/mail-protocol-results.json`. These distinguish local delivery from external delivery. The Dmail third-party notices page links upstream notices; originals remain in the installed packages and build sources. Exact component commits are in `ZIMBRA-SOURCE-MANIFEST.txt`.

Certificate renewal dry-run passed. After installing the compatibility bridge, a full restart completed and the missing Log4j class error was absent from new startup output.

Configured private snapshot: `/opt/zimbra-build/backups/configured/configuration.tgz`, containing Dmail/nginx/firewall/certificate/Zimbra configuration. It contains secrets and is root-only. It does not contain mailbox data; keep an off-server consistent mail/LDAP backup before business launch.
