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

1. Download `GuardianNodeServerSetup-0.1.0-alpha.1.exe` from the official
   GitHub release and verify the published SHA-256 checksum.
2. Run the installer as an administrator. The alpha installer is unsigned, so
   Windows SmartScreen, Defender, or other antivirus software may warn before
   trust reputation exists.
3. On **Server access**, choose one:
   - **Only this PC** for an all-local parent dashboard.
   - **Private LAN/VPN child PCs can connect** when this PC will pair child PCs.
4. If you choose private LAN/VPN, enter the exact host or IP the child installer will use, such as `192.168.1.42` or `guardian-server.local`. The installer writes the allowed-hosts setting and opens TCP 8787 for the Windows **Private** firewall profile.
5. The installer detects hardware, installs/pulls the AI model, starts the backend, and opens the local setup page.
6. Use the Start Menu **Show Setup Token** shortcut, enter that token in the setup page, then create the parent account and recovery code.
7. Write down the child installer URL, for example `http://192.168.1.42:8787`.

Power users doing a silent Windows server install can enable the same private
LAN/VPN mode with:

```powershell
GuardianNodeServerSetup-0.1.0-alpha.1.exe /VERYSILENT /LAN=1 /SERVERHOST=192.168.1.42
```

### If your server is Linux

Open a terminal, download the tagged installer script, verify the published
checksum or signature, review it locally, then run it:

```bash
curl -fsSLO https://raw.githubusercontent.com/the-vibe-dev/guardiannode/v0.1.0-alpha.1/installer/server-linux/install.sh
# Verify the published checksum or signature before running:
sudo bash install.sh
```

Or with Docker (if you prefer):
```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode/installer/server-linux
docker compose up -d
```

For a native Linux server that child PCs will reach on a trusted private
LAN/VPN, set the bind address and allowed host list during install:

```bash
sudo GN_BIND_HOST=0.0.0.0 \
  GN_ALLOWED_HOSTS=127.0.0.1,localhost,192.168.1.42,guardian-server \
  bash install.sh
```

Replace `192.168.1.42` and `guardian-server` with the exact server LAN IP or
hostname the child installer will use. Keep TCP 8787 firewalled to trusted child
PCs only.

For the native installer, open `http://127.0.0.1:8787/setup` on the server and
enter the printed one-time setup token. For Docker, open
`http://127.0.0.1:8787/setup` on the Docker host and read the token from the
container logs or data volume.

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

1. Copy `GuardianNodeChildSetup-0.1.0-alpha.1.exe` from the official GitHub
   release to the kid's PC and verify the published SHA-256 checksum.
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

For a stronger alpha smoke test, use a known-safe synthetic test phrase and
confirm a risk event appears in the dashboard. Do not test with real child
private messages. Logs are under `C:\ProgramData\GuardianNode\logs\` on Windows
and the systemd journal on native Linux servers.

## Stop, disable, or uninstall

- Windows server: Start Menu -> **GuardianNode Server** -> **Stop service**.
- Windows child PC: use the visible GuardianNode tray icon to pause monitoring,
  or uninstall from Windows Settings / Programs & Features as an administrator.
- Native Linux server: `sudo systemctl stop guardiannode-backend`.
- Windows uninstall removes services, scheduled tasks, and installed program
  files. GuardianNode data under `C:\ProgramData\GuardianNode` may be retained
  so parents can back up keys, logs, and evidence intentionally.
- See [Troubleshooting](troubleshooting.md) for manual cleanup steps if
  uninstall is interrupted.

## Pausing on the child's PC

When you use the kid's PC, right-click the GuardianNode tray icon → **Pause monitoring** → enter your parent password. In separated mode, local tray password verification requires either a local parent hash or an HTTPS backend URL; use the dashboard **Devices → Pause** button for plain-HTTP LAN setups.

## Multiple children

For each additional child PC, repeat Step 3 — just create a new pairing code from the dashboard for each device. You can manage multiple children and devices from one parent server.

## Got stuck?

- The child PC installer requires the server URL explicitly in this alpha. Use the parent server's trusted VPN/TLS URL after first-run setup is complete.
- See [Troubleshooting](troubleshooting.md) for more.
