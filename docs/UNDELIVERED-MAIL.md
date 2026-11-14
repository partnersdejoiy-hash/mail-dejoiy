# Undelivered mail: nothing vanishes silently

Rule: any message a person sent that was not delivered must reach them as a clear message
(a bounce, or an error on screen with the message kept in Drafts). Mail coming in from
outside is never bounced (that would be backscatter spam); it goes to quarantine or Junk,
and the mailbox owner or company admin can see that something was stopped.

## What happens where

| Where it stops | Outgoing (our users) | Incoming (outside senders) |
|---|---|---|
| Virus (ClamAV via amavis) | bounce to sender, plain-language reason, quarantined | discarded + quarantined, recipient and admin warned |
| Banned file type | bounce to sender | discarded + quarantined (no bounce) |
| Spam (score >= kill level) | bounce to sender | delivered to Junk |
| Password-protected PDF/Office/zip | allowed (`zimbraVirusBlockEncryptedArchive FALSE`) | allowed |
| Too big | refused while sending (app error, or SMTP 552) | refused at SMTP (sender's server tells them) |
| Remote server says no | Postfix bounce to sender (SES bounces come back by mail) | - |
| Cannot deliver yet | "delayed" notice after 4 h, bounce after 3 days | - |
| Web send refused by Zimbra | error on screen, message kept in Drafts (never Sent), logged | - |

## Server pieces

* `deploy/zimbra-overrides/` - amavis rules Zimbra has no setting for (bounce outgoing
  virus/banned/spam, never bounce incoming, readable bounce text). `apply.sh` installs them
  and adds one include line (marked `DMAIL-OVERRIDE`) to `amavisd.conf.in`.
  **After every Zimbra upgrade:** `sudo bash deploy/zimbra-overrides/apply.sh && su - zimbra -c 'zmamavisdctl restart'`.
  A daily timer (`dmail-zimbra-overrides-check.timer`) runs `apply.sh --check --notify` and
  mails admin@corp.dejoiy.com if anything drifted.
* Zimbra settings (LDAP, survive upgrades): `zimbraVirusBlockEncryptedArchive FALSE` (global),
  `zimbraMtaDelayWarningTime 4h`, `zimbraMtaMaximalQueueLifetime 3d`, `zimbraMtaBounceQueueLifetime 3d`
  (server); localconfig `smtp_source`/`smtp_destination = admin@corp.dejoiy.com`.
* `server/undelivered.py` + `dmail-undelivered-index.timer` - root reads the Postfix and amavis
  logs every 5 minutes and writes `/var/lib/dmail/undelivered.db` (root:dmail 0640, envelope data only).

## Admin console: Monitor > Undelivered mail

Last 14 days: stopped, bounced, refused, still waiting, and web sends Zimbra refused. Each row:
when, from, to, what happened, why, and whether the sender (or recipient) was told. "Nobody told"
rows are highlighted. Company admins see only rows whose sender or recipient is in their domain
(needs the "Add and edit mailboxes" permission); the platform team sees everything.

## Install / update the timers

```
sudo cp /opt/mail-dejoiy/deploy/dmail-undelivered-index.{service,timer} /etc/systemd/system/
sudo cp /opt/mail-dejoiy/deploy/zimbra-overrides/dmail-zimbra-overrides-check.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dmail-undelivered-index.timer dmail-zimbra-overrides-check.timer
```
