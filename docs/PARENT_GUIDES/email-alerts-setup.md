# Get alerts by email

GuardianNode can email you the moment a serious alert fires (and quietly log the
rest). Setup is a dropdown plus an app password.

Dashboard → **Settings** → **Email alerts**.

## 1. Pick your provider

Choose your email provider from **Quick setup**. GuardianNode fills in the server,
port, and security settings for you:

| Provider | What you still need |
|---|---|
| **Gmail** | An **App Password** (not your normal password) |
| **Outlook / Hotmail** | Your full address as the username; app password if you use 2-step |
| **Yahoo Mail** | An **App Password** |
| **iCloud Mail** | An **app-specific password** |
| Other / custom | Enter your provider's SMTP host/port manually |

## 2. App passwords (the one gotcha)

Most providers won't let an app sign in with your normal password — you create a
separate "app password" just for GuardianNode:

- **Gmail:** Google Account → Security → 2-Step Verification (turn on) → App
  passwords → generate one → paste it as the password here.
- **Yahoo:** Account Security → Generate app password.
- **iCloud:** appleid.apple.com → Sign-In and Security → App-Specific Passwords.

The dashboard shows the right hint for whichever provider you pick.

## 3. Fill in the rest

- **Username** — usually your full email address.
- **Password** — the app password from step 2.
- **From address** — your email address (where alerts appear to come from).
- **To address** — where you want alerts sent (can be the same address or a
  different one, e.g. both parents).
- Tick **Email alerts enabled**.

## 4. Test it

Click **Send test**. A test message is sent and the result is recorded on the
**Audit** page (success or the exact error — your password is never logged).
If it fails, the most common cause is using your normal password instead of an
app password.

## What gets emailed?

By default, **high and critical** alerts email you immediately; lower-severity
and "monitored" items stay in the dashboard without pinging you. You control
which categories alert vs. monitor per child in
[Privacy & alert settings](privacy-and-alert-settings.md).

## Prefer push instead of email?

There's also a **Webhook URL** field that works with self-hosted push services
like [ntfy](https://ntfy.sh) or Gotify — paste your topic URL and immediate
alerts are POSTed there as JSON. Nothing leaves your network if you self-host it.
