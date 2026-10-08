# Dmail feature coverage

This is implementation coverage, not proof of production acceptance. The current
workspace cannot reach the public service, launch Chromium, or write to `/opt`.
AOL and Zoho accounts have not been inspected in a signed-in browser. Credentials
must not be added to this repository.

| Area | Implementation in this branch | Remaining work |
|---|---|---|
| Mail | Send, reply/reply-all, forward, drafts, attachments, folders, read/star, labels, search, sorting | Live regression acceptance, server-side search across unloaded messages |
| Appearance | Six photo presets, custom photo upload, light/medium/dark, color themes, list/split reader | Verify remote photo availability and desktop/mobile rendering |
| Admin access | Server-derived account capabilities; normal users have no admin link or view; separate upstream admin authentication and CSRF checks | Live administrator and normal-user acceptance |
| Mailbox roles | Explicit User/Admin on creation; full admins can change roles; delegated admins cannot grant full admin; own-role changes rejected | Delegated scope/right assignment UI; session revocation verification |
| Mailbox management | Create, lock/reactivate/maintenance, password reset, quota, aliases | Delete/restore, account lifecycle, batch provisioning/import, audit trail |
| Domains | List and create | Verification, domain policies, aliases, DNS checks, domain deletion lifecycle |
| Groups | Not integrated | Distribution lists, membership, owners, moderation, permissions |
| Policies | Not integrated | Classes of service, password policy, retention, forwarding rules, feature controls |
| Operations | Not integrated | Server/service monitoring, queues, logs, storage, backups and restore |
| Organization security | Upstream auth and separate admin tokens | SSO/MFA management, active sessions, organization audit logs |
| Collaboration | Contacts integrated; calendar/tasks/chat remain demo-only and hidden in live mode | Server calendar/tasks, sharing, delegated mailboxes, invitations |
| Migration | Not integrated | Import/export, migration jobs, status and retries |

The old gradient presets are explicitly labelled **Illustrated gradients**, not
photo themes. New photo presets load `images.unsplash.com` in the user's browser;
custom uploaded photos remain in browser preferences. Cached/self-hosted licensed
photo assets should replace remote URLs if offline operation is required.

An administration operation is never authorized by the visible dropdown or client
flags. The adapter uses the independently authenticated admin token and upstream
permissions. Full-admin grants additionally fetch the actor's current account and
check its full-admin attribute on the server. No shared super-admin credential is
used. Demotion does not make a promise of immediately invalidating existing
upstream tokens; their expiry/revocation behavior needs deployment acceptance.

Reference scope:
- [AOL settings](https://help.aol.com/articles/aol-mail-mail-settings)
- [Zoho Admin Console](https://www.zoho.com/mail/help/adminconsole/overview.html)
- Installed Zimbra 10.1.21 source: `GetInfo.java`, account-info attributes, and
  administrator SOAP operations in `/opt/zimbra-build/work/zm-mailbox`.

## Acceptance after deployment

1. Sign in as an ordinary user: no admin navigation, direct admin route denied,
   `/api/admin` and admin mutations denied without an upstream admin session.
2. Sign in as a full admin, verify its password, create a User mailbox, then an
   Admin mailbox, and verify each account's effective upstream permissions.
3. Confirm a delegated admin cannot grant full-admin roles, including forged API
   requests; verify own-role demotion is rejected.
4. Change a test mailbox quota, add/remove an alias, and check upstream state.
5. Apply each photo, toggle all brightness modes, reload, and check mobile and
   desktop readability. Confirm changing back to Pearl removes the photo.
6. Run mail send/receive, attachments, drafts and contacts regression checks.

The staging package at `/root/dmail-ui-release` now includes the adapter changes;
frontend-only deployment is insufficient for the new permission and role fields.
