# Install GuardianNode with a separate server + child PC

This guide is for advanced alpha operators testing a separate parent-owned
server and child PC. GuardianNode 0.1.0-alpha.1 does not recommend separated
raw-LAN HTTP for ordinary family use; use a trusted VPN/TLS setup and keep the
backend off the public internet.

## Before you start

You'll need:
- One PC for the **server**: Windows 10/11 **or** Linux, ideally with 16+ GB RAM and a GPU (works without a GPU but is slower)
- One PC for the **child**: Windows 10/11
- Both on the same home network
- About 45 minutes total
- A pen and paper for the recovery code

## Step 1 — Install the server first

### If your server is Windows

1. Build the server installer from source or use a maintainer-provided alpha test artifact.
2. Run the installer.
3. The installer detects hardware, installs/pulls the AI model, starts the backend on `127.0.0.1`, and opens the local setup page.
4. Use the Start Menu **Show Setup Token** shortcut, enter that token in the setup page, then create the parent account and recovery code.
5. To use a child PC during this alpha, place the server behind a trusted VPN/TLS path first. If you are deliberately running a private lab LAN test, manually edit `%ProgramData%\GuardianNode\server.env` as an administrator:
   ```text
   GUARDIANNODE_BIND_HOST=0.0.0.0
   GUARDIANNODE_ALLOWED_HOSTS=192.168.1.42,guardian-server,127.0.0.1,localhost
   GUARDIANNODE_MDNS_ENABLED=false
   ```
   Replace `192.168.1.42` and `guardian-server` with the actual server LAN IP
   or hostname that the child PC will use.
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
Environment="GUARDIANNODE_ALLOWED_HOSTS=192.168.1.42,guardian-server,127.0.0.1,localhost"
Environment="GUARDIANNODE_MDNS_ENABLED=false"
```

Replace the example IP/hostname with your server's actual LAN address/name.

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart guardiannode-backend
```

Docker Compose keeps the host port bound to loopback by default. Change the
backend port mapping to `8787:8787`, then run `docker compose up -d` again.

Separated mode currently uses local-network HTTP unless you add TLS, Tailscale,
WireGuard, or a trusted reverse proxy. Treat raw LAN HTTP as a private lab test
only, not a supported family deployment.

## Step 2 — Open the dashboard and prepare a pairing code

Go to your dashboard URL (e.g. `http://192.168.1.42:8787`). Sign in.

Click **Devices** in the left sidebar → **Add Device**. The dashboard shows you:
- A **6-digit pairing code** (valid for 10 minutes)

Keep this page open while you walk to the kid's PC.

## Step 3 — Install on the child's PC

1. Build the child installer from source or copy the maintainer-provided alpha test artifact to the kid's PC.
2. Run it. (See [SmartScreen guide](when-windows-says-protected-your-pc.md) if Windows complains.)
3. On wizard page 2, pick **"Connect to existing GuardianNode server"**.
4. Enter the explicit trusted VPN/TLS server URL. Use a raw `http://192.168...` URL only in a private lab test.
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

- The child PC installer requires the server URL explicitly in this alpha. Use the parent server's trusted VPN/TLS URL after first-run setup is complete.
- See [Troubleshooting](troubleshooting.md) for more.
