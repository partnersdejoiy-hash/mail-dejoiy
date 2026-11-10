# Dejoiy Mail on Google Play

Two Android apps, both Trusted Web Activities: they open the live sites full screen, with no browser
bar, using Chrome on the phone. Every web deploy updates the apps at once; a new Play upload is only
needed to change the icon, name or Android settings.

| App | Package | Opens |
|---|---|---|
| Dejoiy Mail | `com.dejoiy.mail` | https://mail.dejoiy.com/ |
| Dejoiy Mail Admin | `com.dejoiy.mail.admin` | https://admin-mail.dejoiy.com/admin |

Store texts and graphics are in `store/mail` and `store/admin`.

## 1. Create the upload key (once)
On a computer with Java:
```
bash tools/android-keystore.sh dejoiy-upload.jks
```
It prints a password reminder, the keystore as base64, and the upload key's SHA-256 for each app.
Keep `dejoiy-upload.jks` and its password private and backed up. Never commit it.

## 2. Add the GitHub secrets
Repository > Settings > Secrets and variables > Actions > New repository secret:
- `DMAIL_UPLOAD_KEYSTORE_BASE64`: the base64 text
- `DMAIL_KEYSTORE_PASSWORD`: the password

## 3. Build
Actions > **Android apps** > Run workflow, version code `1`, version name `1.0.0`.
Download the artifacts: `app-release.aab` for each app. Every later upload needs a higher version code.

## 4. Play Console
For each app: Create app > upload the `.aab` to Internal testing first, turn on Play App Signing (the default), and fill in the listing from `store/<app>/listing.md`.
- Privacy policy: https://mail.dejoiy.com/privacy
- App access: give a test login (the apps need sign-in)
- Data safety: email address, name, messages and files (to run the service), not sold, not shared for ads, encrypted in transit, users can ask for deletion
- Target audience: 18 and over · Ads: none

## 5. Link the apps to the sites (removes the browser bar)
Play Console > Setup > App signing: copy the **SHA-256** of the app signing key (and of the upload key).
Paste them into `server/android-apps.json` under `mail` or `admin`, then deploy. Check:
https://mail.dejoiy.com/.well-known/assetlinks.json and https://admin-mail.dejoiy.com/.well-known/assetlinks.json

Until the fingerprints are live, the apps still work but show a small address bar at the top.

## Changing the apps
Edit `android/<app>/twa-manifest.json`, then regenerate with Bubblewrap:
```
npm i @bubblewrap/core && (cd web && python3 -m http.server 8766 &) && ICON_BASE=http://127.0.0.1:8766 node tools/android-generate.cjs
```
Re-apply the signing block in `app/build.gradle` if the generator overwrote it, bump the version code, and build again.
