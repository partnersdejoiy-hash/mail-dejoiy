# Dejoiy Mail: Admin guide

> **Found a bug or something that does not work as written here?** Do not email it. Open the account menu (your photo, top right) → **Report a bug**, or **Help desk** → **Report a bug**, and describe what you did, what you expected and what happened. Your report goes to your Company admin; a company admin's report goes to the Dejoiy team.

This guide is for **company admins**: the people who look after their company's mailboxes in the **admin console**. It uses the words you see on screen. For reading and sending mail, see the [User guide](USER-GUIDE.md).

Features marked *(not yet tested on live)* are in the console, but nobody has tried them on the live server since they were added.

## Opening the admin console

1. Sign in to Dejoiy Mail with an admin mailbox.
2. Open **Admin** in the left menu. The console opens on its own site (admin-mail.dejoiy.com).
3. For safety, it asks for your password again (**Confirm it's you**). Admin access locks after 15 minutes; enter your password again to go on. **Lock** locks it at once.

The menu on the left has five groups: **Monitor**, **Manage**, **Configure**, **Tools** and **Search**, and **Help** opens this guide. **Open mail** takes you back to your mailbox.

Your **role** decides what you may do. If a page says "Your role does not allow this", ask an admin who manages roles.

## Accounts

**Where:** Manage → **Accounts**.

**What you can do:** see every mailbox, **Export CSV**, create one with **+ New mailbox**, and use the two buttons on each mailbox. **Details** opens all its settings (profile, features, password rules, limits, **Out of office**). **Manage** has the tabs **Profile**, **Access**, **Storage**, **Forwarding** (up to 10 addresses), **Aliases**, **Password** and **Delete**.

> **Keep in mind:** **Delete** removes the mailbox and all its mail for ever. You must type the address to confirm.

### Templates: Onboard, Offboard, Suspend, Reactivate

**What it is:** ready-made jobs that do several steps at once. Each step shows ✓ when it worked or ✗ when it did not.

**Where:** Manage → Accounts → **Templates** → **Use** next to the job.

**Onboard a new employee**

1. Fill in **Full name**, **Email address**, **First password**, **Department**, **Designation**, and tick the mailing lists under **Add to mailing lists**.
2. Tap **Create and set up**.

It creates the mailbox with that password and your company's default mailbox policy, then sets the department and designation, then adds the person to the lists you ticked. If creating the mailbox fails, nothing else is done.

> **Keep in mind:** Onboard does not by itself make the person change the first password, and it sends no welcome mail. Give them the password yourself. To make them change it, open the mailbox's **Details** → **Password** → tick **Must change password at next sign-in**. They can also change it in Settings → Accounts → **Change password**.

**Offboard an employee**

1. Choose the mailbox. (Your own is not in the list.)
2. Leave ticked, or untick: **Lock sign-in**; **Sign them out everywhere** (sets a new random password nobody is shown); **Remove from their department and every mailing list**.
3. Optionally enter **Forward their new mail to**. A copy also stays in their mailbox.
4. Tap **Offboard**.

The steps run in this order: forwarding, removing from the department and lists, the new password, then the lock. The mailbox and its mail are kept; delete it later from **Manage** → **Delete** if you need to.

> **Keep in mind:** forwarding fails if the person's mailbox policy does not allow forwarding. Offboard does not set an out-of-office reply; set one in the mailbox's **Details** → **Out of office** if you want one.

**Suspend** locks sign-in until you reactivate the mailbox. Mail keeps arriving.
**Reactivate** makes a locked mailbox active again.

> **Keep in mind:** you cannot lock your own mailbox.

## Teams & roles

**Where:** Manage → **Teams & roles**.

### Departments

**What it is:** a department (IT, HR, Sales…) is a mailing list with its own address. People in a department see its tickets in **Help desk**, and others can mail them all with `@dept:<department>`.

1. Tap **+ New department**, enter the **Department name** and **Department email**, and tap **Create department**.
2. Tap **People** on a department to add or remove people. A person can be in only one department.
3. **Delete** removes the department. Its address stops working.

### Roles

**What it is:** a role is a designation (like "Team lead") with a set of permissions. A person's role is their **Designation**.

1. Tap **+ Add role** and type a name (up to 40 characters).
2. Choose the access: **Mail only** or **Company admin**.
3. Tick the permissions (see the table).
4. Tap **Save roles**. **Remove** takes a role away.

| Permission | What it lets the person do |
|---|---|
| Post in the company box | Post updates in the Company page everyone sees |
| Add and edit mailboxes | Create mailboxes and change their details |
| Delete mailboxes | Delete mailboxes for ever |
| Manage departments and team lists | Create and change departments and mailing lists |
| See the DNS setup | Open Domains → DNS setup |
| Manage roles, permissions and the company box | Change this page, policies, branding, mail service, webhooks and API tokens |
| See and handle every help desk ticket | See every ticket in the company, answer it and change it, like a company admin does |

A **Mail only** role can have only "Post in the company box" and "See and handle every help desk ticket". A company admin with no role gets every permission. The ready-made roles are Member, Team lead, Department head and IT admin.

You can keep **1 to 30 roles**. *(30 roles is not yet tested on live.)*

> **Keep in mind:** roles, policies and the company box name share one small space on the mail server. If you see "That is more than the mail server can keep for one company", use shorter names or fewer roles.

### Company box

The **Company box** is the Company page every mailbox sees. Give it a name and tap **Save name**. Only people whose role has "Post in the company box" can post there.

## Domains

**Where:** Manage → **Domains**. Each domain has the buttons **Settings**, **DNS setup**, **Branding & sign-in** and **Mail service**.

### DNS setup

**What it is:** the records your domain needs so mail reaches you and leaves you safely.

1. Tap **DNS setup**. You see the records: **MX**, **SPF**, **DKIM** and **DMARC**.
2. Use **Copy** to copy each one into your domain provider's DNS page.
3. Tap **Check again**. Each record shows **Live**, **Preparing**, **Needs a fix** or **Not found**.

> **Keep in mind:** if you already have an SPF record, the one shown is your old one with Dejoiy Mail added. Replace the old one; never keep two SPF records. DKIM shows "Preparing" until its key is ready.

### Branding & sign-in

**What it is:** your company's look on the sign-in page, and an optional sign-in address of your own (like `mail.yourcompany.com`).

1. Enter the **Name**, **One line on the sign-in page**, and the **Button colour on the sign-in page**.
2. **Choose logo** (PNG or JPG, up to 200 KB) and **Choose sign-in background** (PNG or JPG, up to 600 KB).
3. Tap **Save name, logo and background**. **Remove logo** and **Remove picture** take them away.
4. For your own sign-in address: first add a **CNAME** record for it at your domain provider, pointing to the mail server. Then enter it in **Your address** and tap **Save address**.

The server gets a security certificate for your address by itself, within about 10 minutes. Only mailboxes of your company can sign in there.

> **Keep in mind:** the address must be under your own domain, and its DNS must already point to the mail server when you save. You can have one such address. Logos and backgrounds are public pictures.

### Mail service (your own sending service) *(not yet tested on live)*

**What it is:** send your company's mail to the outside world through a service you already pay for (Amazon SES, Resend, Brevo, Mailgun, Postmark, SendGrid or any SMTP server), so it carries your company's sending reputation.

1. Tap **Mail service**. Pick your provider in **Quick fill**, or type the details:
   - **SMTP server**, for example `email-smtp.ap-south-1.amazonaws.com` or `smtp.resend.com`
   - **Port**: 587 (with **STARTTLS**) or 465 (with **SSL**); 2587, 2465 and 25 also work
   - **User name** and **Password or API key**, as your provider gave them
2. Under **Who uses it**, tick departments, or tick none so everyone uses it.
3. Leave **Switched on** ticked and tap **Save**.
4. Tap **Send me a test mail**. It goes to your own address.

It is used only for mail to addresses **outside** your company. The sender's copy still goes to their Sent folder. **Remove** goes back to Dejoiy Mail's own sending.

**How the password is kept:** it is stored encrypted on the server, with the key in a separate file only the mail app can read. It is never sent back to your browser, so the box stays empty after you save. To keep the saved password, leave the box empty (this works only if the server and user name stay the same). Someone with full (root) access to the server could still read it.

> **Keep in mind:** the server must be reachable on the public internet. If your provider changes your key, enter the new one here, or mail to the outside will fail.

## Help desk tickets *(not yet tested on live)*

**What it is:** the tickets your people raise to **Company admin** in **Help desk**. Every company has this team, even with no departments.

**Where:** Monitor → **Help desk tickets**. In your mailbox the same tickets are in **Help desk**, on the tabs **Company admin queue** and **All company tickets**.

**How to use it:**

1. The page shows three lists:
   - **Waiting for your company's admins**: open tickets in your queue (raised to Company admin, or assigned to you).
   - **Open in your company, not picked up by anyone yet**: every open ticket nobody is assigned to, for any team. This catches tickets for a department nobody is in yet.
   - **Every ticket in your company**: all of them, finished ones too.

   The number at the top counts the tickets in the first two lists.
2. Tap **Open** to answer a ticket. It opens in **Help desk** in your mailbox, where you set the status, assign it, change its priority or move it to a department. (How answering works is in the [User guide](USER-GUIDE.md#help-desk-not-yet-tested-on-live).)
3. **Open Help desk** opens the whole Help desk.

### Raising a ticket to the Dejoiy team

1. In your mailbox open **Help desk** → **New ticket** (or **Report a bug**).
2. In **Which team should handle it?** choose **Dejoiy platform (the Dejoiy team)**.
3. Fill in the title, priority and details and tap **Send ticket**.

These tickets have codes like **P-0001**. Only you and the Dejoiy team see them, and they cannot be moved to another team.

> **Keep in mind:** people whose role has "See and handle every help desk ticket" can also raise tickets to Dejoiy.

## Mailbox policies

**Where:** Configure → **Mailbox policies**.

**What it is:** rules for every mailbox: password length and age, locking after wrong passwords, automatic sign-out, emptying Trash and Spam, and whether forwarding, IMAP and POP are allowed.

1. Tap **+ New policy**, name it, set the rules and tap **Create policy**.
2. **Make default** makes new mailboxes follow it. **Edit**, then **Save and apply**, changes it.
3. **Who follows which policy** shows which mailboxes follow which policy.

You can keep 1 to 20 policies.

> **Keep in mind:** saving applies the policy again to every mailbox. Turning forwarding off also removes forwarding addresses people already set.

## Webhooks

**Where:** Configure → **Webhooks**.

**What it is:** Dejoiy Mail tells your own system when something happens: mail received or sent, a sign-in that worked or failed, an admin sign-in or admin action.

1. Tap **Add webhook**, enter an `https://` address and choose the events.
2. Copy the **signing secret** (it starts with `whsec_`). It is shown only once. Your system checks the `X-Dejoiy-Signature` header with it.
3. **Send test** sends a test event. **Switch off**, **Switch on** and **Remove** do what they say.

Up to 5 webhooks per company. A failed delivery is tried 3 times. After 20 failures in a row the webhook switches itself off.

## API tokens

**Where:** Configure → **API tokens**.

**What it is:** a key that lets your own programs send, read or label mail, or post to Shine, without a password.

1. Tap **Make token**, choose what it may do (send mail, label mail, read mail, read mail text, post to Shine) and how long it lasts (7, 30, 90 or 365 days).
2. Copy the token (it starts with `dmk_`). It is shown only once.
3. **Revoke** stops a token at once.

Up to 10 tokens per company. Each token may make 60 calls a minute and send 100 mails an hour.

> **Keep in mind:** a token is as powerful as a password. Give each program its own token, with only what it needs.

## Automations

**Where:** Configure → **Automations**.

- **Important mail to Shine:** mail from up to 50 chosen senders is announced in a Shine channel (at most 30 posts an hour; the mail's text is never posted).
- **Follow-up reminder:** if a mail someone sent gets no answer in 1, 2, 3, 5, 7 or 14 days, they get a reminder in their Inbox. It is checked every hour, and only for mail sent after you switched it on.

## Undelivered mail

**Where:** Monitor → **Undelivered mail**.

**What it is:** mail from the last 14 days that could not be delivered, with the reason. **Nobody told** shows the ones where the sender was not told.

> **Keep in mind:** the list is updated every few minutes, not at once. Some reasons are written in Hindi-English.

## Reports

**Where:** Monitor → **Reports**.

**What it is:** numbers for the last 14 days of mail sent from the web app and Dejoiy apps. Mail sent from other mail apps (IMAP) is not counted.

## Bulk import

**Where:** Tools → **Bulk import**.

1. Make a CSV file with one mailbox per line: `email,display name,password`. A first line starting with `email` is skipped.
2. Tap **Choose CSV file**, then **Check and create**.

Up to 500 mailboxes at a time. They get the default mailbox policy.

> **Keep in mind:** names cannot contain commas.

## Other pages

- **Active sessions** (Monitor): who is signed in. **Sign out everywhere** signs a person out on all devices.
- **Mailbox tools** (Tools): rebuild a mailbox's search, recount its storage, or sign it out everywhere.
- **Distribution lists** and **Resources** (Manage): mailing lists and bookable rooms or equipment.
- **Search directory** (Search): find accounts, aliases, lists and resources.

## Android app *(not yet tested on live)*

**What it is:** two Android apps, **Dejoiy Mail** (for everyone) and **Dejoiy Mail Admin** (this console). Both can be on the same phone.

**Where:** the newest **Dejoiy Mail Android** release from the Dejoiy team has the files `dejoiy-mail-<version>.apk` and `dejoiy-mail-admin-<version>.apk`.

**How to use it:**

1. Send your people the `dejoiy-mail-<version>.apk` file (or a link to it). Install `dejoiy-mail-admin-<version>.apk` yourself.
2. On the phone, open the file. If Android asks, allow installing from this source (Settings → Apps → Special app access → **Install unknown apps**), then tap **Install**.
3. Open **Dejoiy Mail Admin** and sign in with your admin mailbox.

In the admin app, **Open mail** and the **Open** buttons on Help desk tickets open the Dejoiy Mail app if it is installed, and the browser if not.

> **Keep in mind:** only share files from the official release. Each file's SHA-256 is in the release notes, so the Dejoiy team can confirm a file is the real one.

## Only for the Dejoiy team

People on the Dejoiy team (the **global admins**) see more than a company admin:

- Every company and domain, with **+ Add domain**, **Delete** and the domain status, and **Platform limits** in a domain's Settings.
- Server pages: **Server status**, **Server statistics**, **Mail queues**, **Class of service**, **Global settings**, **Admins & rights**, **Add-ons**, **Certificates**, **Retention** and **Server caches**.
- A **Company** picker on Webhooks, API tokens and Automations, and Reports for every company.
- **Chat & meetings** for every company.
- In Help desk tickets: **Raised to Dejoiy by company admins** (and the **From companies to Dejoiy** tab in the mail app's Help desk). Only the Dejoiy team works on P- tickets.
- Mailing every company at once with `@allS`.

> **Found a bug or something that does not work as written here?** Do not email it. Open the account menu (your photo, top right) → **Report a bug**, or **Help desk** → **Report a bug**, and describe what you did, what you expected and what happened. Your report goes to your Company admin; a company admin's report goes to the Dejoiy team.
