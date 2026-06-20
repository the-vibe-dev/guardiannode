# Install GuardianNode with a separate server + child PC

If you have two PCs — for example a gaming PC for your kid and a home-server PC for yourself, or an old laptop you can repurpose — this is the recommended setup. The kid's PC stays fast (no AI runs on it) and they can't easily tamper with the dashboard/evidence.

## Before you start

You'll need:
- One PC for the **server**: Windows 10/11 **or** Linux, ideally with 16+ GB RAM and a GPU (works without a GPU but is slower)
- One PC for the **child**: Windows 10/11
- Both on the same home network
- About 45 minutes total
- A pen and paper for the recovery code

## Step 1 — Install the server first

### If your server is Windows

1. Download `GuardianNodeServerSetup-0.1.0-alpha.1.exe` from [Releases](https://github.com/the-vibe-dev/guardiannode/releases).
2. Run the installer.
3. The installer detects hardware, installs/pulls the AI model, starts the backend on `127.0.0.1`, and opens the local setup page.
4. Use the Start Menu **Show Setup Token** shortcut, enter that token in the setup page, then create the parent account and recovery code.
5. To use a child PC on your LAN during this alpha, manually edit `%ProgramData%\GuardianNode\server.env` as an administrator:
   ```text
   GUARDIANNODE_BIND_HOST=0.0.0.0
   GUARDIANNODE_MDNS_ENABLED=false
   ```
6. Restart the backend service and add a private-network firewall rule:
   ```powershell
   Restart-Service GuardianNodeBackend
   New-NetFirewallRule -DisplayName "GuardianNode Backend (LAN)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8787 -Profile Private
   ```
7. Find the server's LAN IP and write down the dashboard URL, for example `http://192.168.1.42:8787`.

### If your server is Linux

Open a terminal and run:
```bash
curl -fsSL https://raw.githubusercontent.com/the-vibe-dev/guardiannode/v0.1.0-alpha.1/installer/server-linux/install.sh | sudo bash
```

Or with Docker (if you prefer):
```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode/installer/server-linux
docker compose up -d
```

For the native installer, open `http://127.0.0.1:8787/setup` on the server and
enter the printed one-time setup token. For Docker, open
`http://127.0.0.1:8787/setup` on the Docker host and read the token from the
container logs or data volume.

To use a child PC on your LAN during this alpha, manually bind the backend to
the LAN after first-run setup:

Native systemd:

```bash
sudo systemctl edit guardiannode-backend
```

Add:

```ini
[Service]
Environment="GUARDIANNODE_BIND_HOST=0.0.0.0"
Environment="GUARDIANNODE_MDNS_ENABLED=false"
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart guardiannode-backend
```

Docker Compose keeps the host port bound to loopback by default. Change the
backend port mapping to `8787:8787`, then run `docker compose up -d` again.

Separated mode currently uses local-network HTTP unless you add TLS, Tailscale,
WireGuard, or a trusted reverse proxy. Use it only on a trusted LAN/VPN during
alpha testing and do not expose the backend directly to the internet.

## Step 2 — Open the dashboard and prepare a pairing code

Go to your dashboard URL (e.g. `http://192.168.1.42:8787`). Sign in.

Click **Devices** in the left sidebar → **Add Device**. The dashboard shows you:
- A **6-digit pairing code** (valid for 10 minutes)

Keep this page open while you walk to the kid's PC.

## Step 3 — Install on the child's PC

1. Download `GuardianNodeChildSetup-0.1.0-alpha.1.exe` to the kid's PC.
2. Run it. (See [SmartScreen guide](when-windows-says-protected-your-pc.md) if Windows complains.)
3. On wizard page 2, pick **"Connect to existing GuardianNode server"**.
4. Enter the explicit server URL, for example `http://192.168.1.42:8787`.
5. Enter the 6-digit pairing code from your dashboard.
6. Continue the installer.

## Step 4 — Verify

On your phone or any computer on the home network, open the dashboard URL. The new device should appear under **Devices** as online.

Try opening a simple app on the kid's PC. Within a short period, an event may
appear in the **Risk Feed** with risk level "none" or "low" if the pipeline
captures a meaningful screen change. That confirms the pipeline works.

## Pausing on the child's PC

When you use the kid's PC, right-click the GuardianNode tray icon → **Pause monitoring** → enter your parent password. In separated mode, local tray password verification requires either a local parent hash or an HTTPS backend URL; use the dashboard **Devices → Pause** button for plain-HTTP LAN setups.

## Multiple children

For each additional child PC, repeat Step 3 — just create a new pairing code from the dashboard for each device. You can manage multiple children and devices from one parent server.

## Got stuck?

- The child PC installer requires the server URL explicitly in this alpha. Use the parent server's trusted LAN/VPN URL after first-run setup is complete.
- See [Troubleshooting](troubleshooting.md) for more.
