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
Actions > **Android apps** > **Run workflow**. Branch `fix/dejoiy-mail-completion`, version code `1`,
version name `1.0.0`. Every later run needs a higher version code (2, 3, …); the version name is what
people see (1.0.1, 1.1.0, …).

When it is done, the release **Dejoiy Mail Android 1.0.0** (tag `android-v1`) is on the repository's
**Releases** page with four files and their SHA-256 in the notes:

| File | What it is for |
|---|---|
| `dejoiy-mail-1.0.0.apk` | Install Dejoiy Mail on a phone directly |
| `dejoiy-mail-admin-1.0.0.apk` | Install Dejoiy Mail Admin on a phone directly |
| `dejoiy-mail-1.0.0.aab` | Upload to Google Play (Dejoiy Mail) |
| `dejoiy-mail-admin-1.0.0.aab` | Upload to Google Play (Dejoiy Mail Admin) |

Without the two secrets from step 2 the run stops with "Add the upload key secrets first
(android/README.md, steps 1 and 2)". It never releases an unsigned APK (Android will not install one).

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

## Install the APK without Play Store
1. On the phone, open the repository's **Releases** page in Chrome and open the newest
   **Dejoiy Mail Android** release.
2. Under **Assets**, tap `dejoiy-mail-<version>.apk` (for mail) or `dejoiy-mail-admin-<version>.apk`
   (for the admin console). Both can be installed on the same phone. Check that the SHA-256 in the
   release notes matches if you want to be sure the file is the one GitHub built.
3. Open the downloaded file. The first time, Android says the browser is not allowed to install apps:
   tap **Settings**, switch on **Allow from this source** (Settings > Apps > Special app access >
   **Install unknown apps** > Chrome), go back and tap **Install**.
4. Open **Dejoiy Mail** or **Dejoiy Mail Admin** from the home screen and sign in.

Until the fingerprints of step 5 are live, the apps show a small address bar at the top. They work the
same. For the APKs from Releases the fingerprint that counts is the **upload key's** SHA-256 (printed
in step 1), because GitHub signs them with the upload key; Play Store installs use the app signing key. After you install a newer release over an older one, sign-in and settings are kept, as long as
both were signed with the same upload key.

Each app keeps to its own site. Inside an app, a link to the other site (Admin in the mail app, Open
mail in the admin console) opens the other app when it is installed, and the browser otherwise.

## Changing the apps
Edit `android/<app>/twa-manifest.json`, then regenerate with Bubblewrap:
```
npm i @bubblewrap/core && (cd web && python3 -m http.server 8766 &) && ICON_BASE=http://127.0.0.1:8766 node tools/android-generate.cjs
```
Re-apply the signing block in `app/build.gradle` if the generator overwrote it, bump the version code, and build again.
