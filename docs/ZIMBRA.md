# Zimbra backend integration for Dejoiy Mail

This is an independent SOAP adapter connecting the existing Dejoiy frontend to a separately installed Zimbra server. It does not copy or relabel the Zimbra web client. The existing `backend/` Node/Postgres MVP remains separate: its accounts, RBAC, TOTP, provisioning and billing are **not** used by this adapter. Mail users must already exist in Zimbra and log in with their Zimbra credentials. Do not treat this adapter as an extension of the existing backend's security controls.

## Verified upstream

Checked on 2026-10-07 UTC:

- Official release page: https://wiki.zimbra.com/wiki/Zimbra_Releases lists 10.1.21 as the latest 10.1 patch.
- Official FOSS build repository: https://github.com/Zimbra/zm-build
- Selected tag: `10.1.21`, commit `f40c9007407061e74d48cc19a208b0cbfb9685ec`.
- Its `instructions/FOSS_repo_list.pl` includes `zm-mailbox` and related components. Not every component has a `10.1.21` tag; the build script supplies descending fallback tags as demonstrated by the upstream build documentation.
- Core source: https://github.com/Zimbra/zm-mailbox ; SOAP protocol documentation: `store/docs/soap.txt`.

A source tag is not a prebuilt, validated installation. Run `bash scripts/build-zimbra-foss.sh` on a separate VM with the build dependencies documented by upstream. The script builds FOSS and preserves upstream files. A full binary build has not been run in this workspace. Install the resulting package on a supported OS, configure domains/mailboxes, HTTPS, MX, SPF, DKIM and DMARC, and perform a live acceptance test before offering paid mail.

## Run the connected frontend

Python 3.12+, standard library only:

```bash
export ZIMBRA_URL=https://mail.example.com
export APP_ORIGIN=http://localhost:8080
python3 server/zimbra.py
```

Open exactly `http://localhost:8080`, then use an existing Zimbra mailbox login. The adapter serves `web/` and its APIs on the same origin. It never uses an admin token. `ZIMBRA_URL` must use HTTPS with a trusted certificate; redirects are rejected. For a public deployment, set `APP_ORIGIN=https://your-mail-domain`, terminate HTTPS at a reverse proxy, and keep the Python listener private. Set request timeouts and rate limits at the proxy. Running `python3 -m http.server --directory web` or GitHub Pages continues to show the original demo, not live mail.

## Implemented

- Zimbra authentication, expiring server-memory sessions, logout.
- HttpOnly/SameSite cookies, Secure cookies for HTTPS, origin validation and CSRF tokens on mutations.
- Mailbox refresh: latest 50 messages across folders, with escaped text bodies; original HTML is not executed.
- Send and save draft through SOAP; recipient validation; text-only content.
- Read/unread, star, importance, move, archive folder creation, trash and permanent deletion.
- Live mailbox state stays in memory; real message bodies and auth tokens are not written to localStorage.
- Server errors stop send success messages. No automatic send retries.

## Current limits

This is a first integration, not a production mail platform. Latest-50 counts and search apply only to loaded messages; older/custom-folder messages are not fully browsable. Attachment upload/download and rich HTML rendering are pending; attempts to send/save attachments fail explicitly. Empty Trash applies only to loaded trash messages. Labels, filters, contacts/calendar/chat/notes, account settings, storage quota, provisioning and billing are not connected; their demo screens are blocked in live mode. Theme picker remains available.

Sessions and rate limits are per process; restarting logs users out. This server is intended for initial single-process integration behind a reverse proxy, not horizontal production scaling. Login uses Zimbra credentials and does not reuse the existing Node backend's 2FA/RBAC. Zimbra account suspension/expiry is enforced upstream on calls. Browser logout revokes the adapter session; the upstream token remains only until expiry and is no longer retained by the adapter.

The 10 Python tests and 4 JavaScript adapter tests pass. Full browser smoke testing was attempted but the environment has no installed Chromium executable.

A live Zimbra host was not supplied, so no real login/send/receive or DNS deliverability test has been performed. SOAP responses and HTTP security are covered by mocked tests:

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_backend.cjs
node --check web/js/backend.js
```

Live acceptance: sign in with two distinct accounts, receive external mail, refresh, send to an external inbox, save/edit a draft, move/star/read/delete messages, confirm account isolation and logout. Confirm MX/SPF/DKIM/DMARC and inspect delivery/bounce logs before launch.

## Licensing

The adapter is newly written Dejoiy integration code. No Zimbra source is vendored into this repository and no upstream attribution is removed. Zimbra is separately built and installed. Preserve all required licence/copyright notices in that build and in any distribution, and satisfy source-availability obligations for any covered modifications. Verify licences per component and build; Network Edition binaries and proprietary extensions are not included. Official licence overview: https://www.zimbra.com/product/licenses-and-terms-of-use/.
