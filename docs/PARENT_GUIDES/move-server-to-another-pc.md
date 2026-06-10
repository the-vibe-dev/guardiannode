# Move the server to another PC

If you started with an **all-in-one** setup and now want to move the backend onto a separate server PC (so the kid's PC isn't slowed by AI processing), use this migration flow.

## Before you start

You'll need:
- The new server PC (Windows or Linux), already on your home network
- About 30 minutes
- Your parent password and recovery code

## Step 1 — Install GuardianNode on the new server

Follow the [server install guide](install-server-and-child.md) Step 1. **Important**: when the wizard asks if this is a fresh install or a migration, pick **"I'm migrating an existing GuardianNode install"**.

The new server will boot up and show a migration pairing code.

## Step 2 — On the existing all-in-one PC, run the migration tool

1. Open the dashboard at `http://127.0.0.1:8787`.
2. Sign in.
3. Go to **Settings → Migration**.
4. Click **"Move backend to another PC"**.
5. Paste the migration pairing code from the new server.
6. Click **Start migration**.

The tool exports:
- The encrypted SQLite database
- The encrypted evidence blob directory
- Device tokens (rotated as part of the migration)
- Audit logs

…and sends it to the new server over a TLS connection. Speed depends on how much evidence has accumulated — typically 1–10 minutes.

## Step 3 — Verify on the new server

Open the new server's dashboard. All your historical alerts, devices, and settings should be there. Sign in with the same password (or recovery code if you've changed it).

## Step 4 — Reconfigure the kid PC

The migration tool automatically:
- Stops the local backend service on the old (kid) PC
- Uninstalls Ollama from the kid PC (with confirmation — disk space saved: 1–10 GB depending on model)
- Reconfigures the agent to point at the new server
- Removes the old dashboard from the kid PC

The kid PC is now in **separated mode**. The shield icon stays green; events still flow.

## Step 5 — Test

On the kid's PC, open a monitored app for a few seconds. Check the new server's dashboard — events should appear in the Risk Feed within ~10 seconds.

## Rollback

If something goes wrong, the migration tool keeps a backup of the original all-in-one state for 30 days. Go to **Settings → Migration → Rollback** on the new server to roll back.

## Why move?

- **Speed.** Heavy AI classification on the kid's PC slows games. A dedicated server PC (even an older one with a GPU) is much faster.
- **Privacy/tamper.** The kid can't tamper with a backend they don't have physical access to.
- **Backup.** A dedicated server PC is easier to back up.
- **Multiple children.** One server can host multiple kid PCs.

## Multiple servers?

We do not support multiple servers per family in v1 — pick one server PC. If you have multiple children, all their devices report to the same single server.
