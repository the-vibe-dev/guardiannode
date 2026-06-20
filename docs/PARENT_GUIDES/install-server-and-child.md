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
3. The wizard walks you through:
   - Admin account + password + recovery code (write it down!)
   - Network mode — pick **"Other devices on my home network"** (this is the whole point of separated mode)
   - When Windows Firewall prompts, click **Allow access**.
   - Hardware detect → AI model size → automatic download (5–20 minutes)
4. When done, the wizard shows you the dashboard URL like `http://192.168.1.42:8787`. Write it down or bookmark it.

### If your server is Linux

Open a terminal and run:
```bash
curl -fsSL https://raw.githubusercontent.com/the-vibe-dev/guardiannode/main/installer/server-linux/install.sh | sudo bash
```

Or with Docker (if you prefer):
```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode/installer/server-linux
docker compose up -d
```

In both cases, open `http://<server-ip>:8787/setup` in a browser and complete:
- Admin account + password + recovery code
- AI model selection + pull

Separated mode currently uses local-network HTTP unless you add TLS, Tailscale,
WireGuard, or a trusted reverse proxy. Use it only on a trusted LAN/VPN during
alpha testing and do not expose the backend directly to the internet.

## Step 2 — Open the dashboard and prepare a pairing code

Go to your dashboard URL (e.g. `http://192.168.1.42:8787`). Sign in.

Click **Devices** in the left sidebar → **Add Device**. The dashboard shows you:
- A **6-digit pairing code** (valid for 10 minutes)
- A **QR code** containing the same info

Keep this page open while you walk to the kid's PC.

## Step 3 — Install on the child's PC

1. Download `GuardianNodeChildSetup-0.1.0-alpha.1.exe` to the kid's PC.
2. Run it. (See [SmartScreen guide](when-windows-says-protected-your-pc.md) if Windows complains.)
3. On wizard page 2, pick **"Connect to existing GuardianNode server"**.
4. Set up your parent account on this PC (same password as the server is recommended for simplicity).
5. On the "Server connection" page, the installer **automatically searches your network** and shows discovered servers:
   ```
   ✅ Found 1 GuardianNode server on your network:
      ☐ HOME-SERVER (192.168.1.42)
   ```
   Click your server, then click **Next** and enter the 6-digit pairing code from your dashboard.
6. **If no servers are found**, click "Type the address manually" and enter the URL and pairing code by hand.
7. Continue with monitored-apps setup (same as the all-in-one guide).

## Step 4 — Verify

On your phone or any computer on the home network, open the dashboard URL. The new device should appear under **Devices** as online.

Try opening a simple app on the kid's PC. Within a short period, an event may
appear in the **Risk Feed** with risk level "none" or "low" if the pipeline
captures a meaningful screen change. That confirms the pipeline works.

## Pausing on the child's PC

When you use the kid's PC, right-click the GuardianNode tray icon → **Pause monitoring** → enter your parent password.

## Multiple children

For each additional child PC, repeat Step 3 — just create a new pairing code from the dashboard for each device. You can manage multiple children and devices from one parent server.

## Got stuck?

- The child PC installer requires the server URL explicitly in this alpha. Use the parent server's trusted LAN/VPN URL after first-run setup is complete.
- See [Troubleshooting](troubleshooting.md) for more.
