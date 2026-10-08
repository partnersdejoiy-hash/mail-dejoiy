# Zimbra backend integration for Dejoiy Mail

This is an independent SOAP adapter connecting the existing Dejoiy frontend to a separately installed Zimbra server. It does not copy or relabel the Zimbra web client. The existing `backend/` Node/Postgres MVP remains separate: its accounts, RBAC, TOTP, provisioning and billing are **not** used by this adapter. Mail users must already exist in Zimbra and log in with their Zimbra credentials. Do not treat this adapter as an extension of the existing backend's security controls.

## Verified upstream

Checked on 2026-10-07 UTC:

- Official release page: https://wiki.zimbra.com/wiki/Zimbra_Releases lists 10.1.21 as the latest 10.1 patch.
- Official FOSS build repository: https://github.com/Zimbra/zm-build
- Selected tag: `10.1.21`, commit `f40c9007407061e74d48cc19a208b0cbfb9685ec`.
- Its `instructions/FOSS_repo_list.pl` includes `zm-mailbox` and related components. Not every component has a `10.1.21` tag; the build script supplies descending fallback tags as demonstrated by the upstream build documentation.
- Core source: https://github.com/Zimbra/zm-mailbox ; SOAP protocol documentation: `store/docs/soap.txt`.

A source tag is not a prebuilt, validated installation. Run `bash scripts/build-zimbra-foss.sh` on a separate VM with the build dependencies documented by upstream. The script builds FOSS and preserves upstream files. A full FOSS build and host installation completed on the Contabo server; see [CONTABO.md](CONTABO.md) for exact artifacts, runtime repairs, verified local acceptance and pending external delivery. Install the resulting package on a supported OS, configure domains/mailboxes, HTTPS, MX, SPF, DKIM and DMARC, and perform a live acceptance test before offering paid mail.

## Run the connected frontend

Python 3.12+, standard library only:

```bash
export ZIMBRA_URL=https://mail.example.com
export APP_ORIGIN=http://localhost:8080
python3 server/zimbra.py
```

Open exactly `http://localhost:8080`, then use an existing Zimbra mailbox login. The adapter serves `web/` and its APIs on the same origin. It never uses an admin token. `ZIMBRA_URL` must use HTTPS with a trusted certificate; redirects are rejected. For a public deployment, set `APP_ORIGIN=https://your-mail-domain`, terminate HTTPS at a reverse proxy, and keep the Python listener private. Set request timeouts and rate limits at the proxy. Running `python3 -m http.server --directory web` or GitHub Pages continues to show the original demo, not live mail.

## Implemented

- Zimbra authentication, expiring server-side sessions, logout.
- HttpOnly/SameSite cookies, Secure cookies for HTTPS, origin validation and CSRF tokens on mutations.
- Mailbox refresh: latest 50 messages across folders, with escaped text bodies; original HTML is not executed.
- Send and save draft through SOAP; recipient validation; plain and sanitized HTML content.
- Attachment upload/send/draft/download, safe rich-text formatting, Gmail typo validation and atomic removal of a sent draft.
- Real contacts, sender display/signature settings and vacation automatic-reply preferences.
- Independent Dejoiy Mail Admin at `/admin`, using a separate upstream-authorized session for mailbox/domain provisioning, status and password management.
- Read/unread, star, importance, move, archive folder creation, trash and permanent deletion.
- Live mailbox state stays in memory; real message bodies and auth tokens are not written to localStorage.
- Server errors stop send success messages. No automatic send retries.

## Current limits

Mailbox pages contain 50 messages; Load more fetches older messages. Counts and search cover loaded messages. Empty Trash clears the whole upstream Trash folder. Attachment uploads total at most 15 MB, with 20 files; downloads are limited to 25 MB. Rich text keeps supported formatting while removing scripts, tracking images and unsafe links. Custom folders, filters, calendar/chat/notes, storage quota, role changes and billing remain unconnected; their demo features are blocked in live mode. The existing Node/Postgres backend remains separate.

Configure `ZIMBRA_ADMIN_URL` with the private HTTPS admin origin (normally port 7071) to enable `/admin`. The browser never connects to that private endpoint. Administration requires a valid mailbox session, CSRF validation and a separate administrator password check. Admin tokens remain server-side and expire within 15 minutes. Do not open port 7071 publicly. Creating domains does not modify DNS.

Set `SESSION_DB=/var/lib/dmail/sessions.sqlite` for persistent sessions in a service-owned directory with mode 0700. The SQLite file uses mode 0600 and contains sensitive upstream tokens; protect backups accordingly. Without this variable, sessions remain in memory and a restart logs users out. Rate limits remain per process; enforce IP-based login limits at the reverse proxy. This server is intended for initial single-process integration behind a reverse proxy, not horizontal production scaling. Login uses Zimbra credentials and does not reuse the existing Node backend's 2FA/RBAC. Zimbra account suspension/expiry is enforced upstream on calls. Browser logout revokes the adapter session; the upstream token remains only until expiry and is no longer retained by the adapter.

The 27 Python tests and 5 JavaScript adapter tests pass. Live headless Chromium verified Dejoiy Mail login, inbox, compose/send and settings against the installed backend. See CONTABO.md for the current deployment and acceptance evidence.

Real login, local SMTP ingress/self-delivery, mail mutations, drafts, session persistence and authenticated SMTP/IMAP have been verified. External send/receive and public DKIM/DMARC acceptance remain pending. SOAP responses and HTTP security are covered by mocked tests:

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_backend.cjs
node --check web/js/backend.js
```

Live acceptance: sign in with two distinct accounts, receive external mail, refresh, send to an external inbox, save/edit a draft, move/star/read/delete messages, confirm account isolation and logout. Confirm MX/SPF/DKIM/DMARC and inspect delivery/bounce logs before launch.

## Licensing

The adapter is newly written Dejoiy integration code. No Zimbra source is vendored into this repository and no upstream attribution is removed. Zimbra is separately built and installed. Preserve all required licence/copyright notices in that build and in any distribution, and satisfy source-availability obligations for any covered modifications. Verify licences per component and build; Network Edition binaries and proprietary extensions are not included. Official licence overview: https://www.zimbra.com/product/licenses-and-terms-of-use/.
