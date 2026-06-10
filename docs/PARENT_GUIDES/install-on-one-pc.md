# Install GuardianNode on one PC

If your family has only one PC — or if you want a simpler setup — install everything on the same machine your child uses. The parent dashboard will be locked behind your password.

## Before you start

You'll need:
- A Windows 10 or Windows 11 PC
- About 30 minutes
- A pen and paper, or a password manager, to save your recovery code
- About 5–10 GB free disk space (depends on the AI model size)
- Admin access on the PC

## Step 1 — Download

Go to the [GuardianNode releases page](https://github.com/the-vibe-dev/guardiannode/releases) and download the latest `GuardianNodeChildSetup.exe`.

## Step 2 — Run the installer

Double-click `GuardianNodeChildSetup.exe`.

**If Windows says "Windows protected your PC":** That's normal for a beta version — see [When Windows says "Protected your PC"](when-windows-says-protected-your-pc.md) for the safe click-through. We're working on getting a signing certificate to remove this warning.

When User Account Control prompts you, click **Yes**.

## Step 3 — Pick "Install everything on this PC"

On the second wizard page, choose the **first** option. This installs:
- The monitoring agent
- The AI engine (Ollama)
- The parent dashboard

## Step 4 — Create your parent account

- Enter a display name like "Mom" or "Parent"
- Pick a **strong password** you'll remember. The kid must not know this password.
- Write down the 12-word recovery code on paper. Store it somewhere safe (filing cabinet, fireproof box, sealed envelope with your important documents). **If you lose both your password AND this code, you cannot recover your data.**

## Step 5 — Create the child's profile

- Enter the child's name (or a nickname — no real personal info needed)
- Pick the age group: **Under 10**, **10–13**, or **14–17**. This controls how sensitive the alerts are.

## Step 6 — Review what will be monitored

GuardianNode runs in the signed-in Windows session and reviews the visible
screen by default. This means it can catch risky text in simple apps such as
Notepad, browsers, games, chat apps, and any other window that is actually on
screen. App names and window titles are recorded as context for alerts.

It does not collect raw keystrokes, does not read password fields directly, and
does not upload child data to a vendor cloud.

## Step 7 — Hardware detection

The installer checks your PC and recommends an AI model size:
- **Tiny** (8 GB RAM or less) — works on any modern PC, slower
- **Small** (8–16 GB RAM) — good balance
- **Medium** (16+ GB RAM, ideally with a GPU) — fastest and most accurate

Pick the recommended option unless you know better. Click **Next** and the installer downloads the model (1–5 GB depending on tier). This takes 5–20 minutes.

## Step 8 — Self-test

The installer runs a synthetic test to make sure everything works. If any check fails, click the link next to it for help.

## Step 9 — Open the dashboard

Click **Open Parent Dashboard**. Your browser opens to `http://127.0.0.1:8787`. Sign in with your parent password.

The installer starts the monitoring agent and the tray icon for the current
Windows user. It also adds all-user Startup entries so the agent and tray launch
again whenever any Windows account signs in.

## Pausing monitoring when you use the PC

When you (the parent) use this PC, you'll want to pause monitoring so your own activity isn't logged.

Right-click the **GuardianNode tray icon** (looks like a small shield in the system tray near the clock) → **Pause monitoring** → enter your parent password → pick how long (15 min, 1 hour, 4 hours, until reboot).

See [Pause monitoring when you use the PC](pause-monitoring-when-you-use-the-pc.md) for more.

## What happens next

GuardianNode runs in the background. If it detects a risk (grooming, scams, self-harm signals, etc.), it appears in your dashboard with a clear explanation. **Critical alerts** also trigger an immediate notification.

Open the dashboard at any time to review alerts: `http://127.0.0.1:8787` from a bookmark on the same PC, or from your phone if you set up LAN mode in settings.

## Got stuck?

See [Troubleshooting](troubleshooting.md) or open a GitHub issue.
