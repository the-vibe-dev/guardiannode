# Install GuardianNode with a separate server + child PC

This advanced closed-beta layout puts the backend on a parent-owned Windows or
Linux server and capture on a Windows child PC. Connections use GuardianNode's
local family CA and pinned HTTPS. Keep both systems on a trusted private LAN or
VPN and never expose the backend directly to the public internet.

The current installer build still requires clean-machine Windows
requalification before distribution to ordinary families.

## Before you start

You'll need:

- A parent-owned Windows or Linux server, ideally with 16 GB or more RAM.
- A Windows 11 child PC. Windows 10 is not currently qualified.
- A trusted private LAN or VPN connecting them.
- Administrator access and about 45 minutes.
- Private storage for the recovery phrase and `.gnpair` trust bundle.

## 1. Install the server

### Windows server

1. Verify the release SHA-256, then run
   `GuardianNodeServerSetup-0.1.0-alpha.3.exe` as administrator.
2. Choose **Private LAN/VPN child PCs can connect**.
3. Enter the exact child-reachable hostname or fixed IP, such as
   `guardiannode.local` or `192.168.1.42`. The installer includes it in the
   server certificate, allowed-host list, and Private-profile firewall rule.
4. Let the installer finish the model and backend checks.
5. Open `https://127.0.0.1:8787/setup`, use the Start Menu **Show Setup Token**
   shortcut, create the parent account, save the recovery phrase, and complete
   the consent checklist.

Silent Windows server example:

```powershell
GuardianNodeServerSetup-0.1.0-alpha.3.exe /VERYSILENT /LAN=1 /SERVERHOST=guardiannode.local
```

### Native Linux server

Download the tagged script, verify its published checksum or signature, review
it locally, then run it. To serve child PCs, specify the exact trusted names or
IPs before installation:

```bash
sudo GN_BIND_HOST=0.0.0.0 \
  GN_ALLOWED_HOSTS=127.0.0.1,localhost,192.168.1.42,guardiannode.local \
  bash install.sh
```

Open `https://127.0.0.1:8787/setup` on the server and enter the printed setup
token. The service generates its family CA and HTTPS certificate on first
start. Keep TCP 8787 firewalled to the trusted child PCs or VPN only.

### Docker Compose

```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode/installer/server-linux
docker compose up --build -d
```

Compose publishes `127.0.0.1:8787` by default. A separated deployment requires
the host-network override or an explicit private port mapping, exact
`GUARDIANNODE_ALLOWED_HOSTS`, and a matching certificate name. See
[Secure LAN setup](../SECURE_LAN_SETUP.md). Do not change the mapping to a
publicly reachable interface.

## 2. Create the secure pairing transaction

Open the dashboard at the exact child-reachable HTTPS URL shown during setup,
for example `https://guardiannode.local:8787`, and sign in. If using a different
parent browser, trust the family CA on that parent-managed device first.

Go to **Devices -> Add device**. The dashboard provides:

- A six-digit, single-use code valid for 10 minutes.
- The exact HTTPS server URL.
- CA check words and a SHA-256 fingerprint.
- A short-lived `.gnpair` trust bundle.

Download the bundle, transfer it privately to the child PC, and compare the CA
check words before continuing. The bundle does not contain a device bearer
token, but delete it after pairing.

## 3. Install the child PC

1. Verify and run `GuardianNodeChildSetup-0.1.0-alpha.3.exe`.
2. Choose **Connect to existing GuardianNode server**.
3. Enter the exact HTTPS URL and six-digit code from the dashboard.
4. Select the transferred `.gnpair` file.
5. Finish installation. The SYSTEM endpoint broker validates the bundle,
   consumes the one-time code, stores the CA and credential under protected
   ProgramData, and launches authorized capture helpers in active sessions.

Silent child example:

```powershell
GuardianNodeChildSetup-0.1.0-alpha.3.exe /VERYSILENT /MODE=child /SERVERURL=https://guardiannode.local:8787 /PAIRCODE=506755 /PAIRBUNDLE=C:\SafeTransfer\pairing.gnpair
```

Plain LAN HTTP is rejected. The only HTTP exception is an explicit loopback
source-development configuration, which must never carry family data.

## 4. Verify the complete path

1. In **Devices**, assign the new device to the correct child profile and
   confirm it becomes online.
2. Confirm the tray icon remains visible in the child session.
3. Use only a documented synthetic canary phrase; never use a child's real
   private conversation as a test.
4. Confirm capture, OCR/classification, alert creation, and parent review.
5. Reboot and repeat the synthetic test. Also test sign-out/sign-in and user
   switching before relying on a current build.

Logs are under `C:\ProgramData\GuardianNode\logs\` on Windows and the systemd
journal on native Linux.

## Pause or remove monitoring

Use the authenticated dashboard **Devices** page to pause or resume. The tray
links to that page and never asks the child session for a parent password.

Uninstall from Windows Settings as an administrator. Windows uninstall removes
services, the tray task, any legacy agent task, firewall rules, and installed
program files; retained ProgramData is reported so keys and evidence are not
silently destroyed. Stop native Linux with
`sudo systemctl stop guardiannode-backend`.

For each additional child PC, create a separate pairing transaction and bundle.
See [Troubleshooting](troubleshooting.md) if any stage fails.
