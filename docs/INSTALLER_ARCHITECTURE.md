# Installer Architecture

## Installers

| Installer | Target | Tech | Output |
|---|---|---|---|
| Child Device (Windows) | Kid's Windows 10/11 PC, or all-in-one parent/child PC | Inno Setup 6 + PyInstaller bundle | `GuardianNodeChildSetup-0.1.0-alpha.1.exe` |
| Server (Windows) | Parent's Windows server PC | Inno Setup 6 + PyInstaller backend bundle | `GuardianNodeServerSetup-0.1.0-alpha.1.exe` |
| Server (Linux) | Parent's Linux server PC | Shell script + systemd / Docker | `install.sh` + Docker Compose |

## Build Pipeline

`installer/build/build_all.sh` stages PyInstaller bundles, copies the built Vite
dashboard, verifies pinned WinSW/Inno downloads, and compiles the Inno scripts.
Release mode fails closed unless real prebuilt bundles are supplied.

## Child Device Installer

The shipped child installer is implemented in
`installer/child-device-windows/GuardianNodeChildSetup.iss`.

Flow:

1. Choose all-in-one mode or connect to an existing server.
2. Select the child age group.
3. In separated mode, enter the explicit server URL and pairing code from the parent dashboard.
4. In all-in-one mode, run a hardware probe and choose the model tier.
5. Install the agent, tray, watchdog services, optional backend, and scheduled logon tasks.
6. Open the dashboard only when the installer knows the dashboard URL.

The agent and tray run in the signed-in Windows user session because service
session 0 cannot capture the desktop. Watchdog services are resilience helpers.

The alpha does not ship a tested password-gated uninstaller wrapper. Uninstall
protection relies on normal Windows administrator/UAC permissions plus service
ACLs; do not describe uninstall as password-gated until a clean-machine Windows
test proves that end-to-end path.

## Windows Server Installer

The shipped server installer is implemented in
`installer/server-windows/GuardianNodeServerSetup.iss`.

Flow:

1. Probe hardware and choose the model tier.
2. Install Ollama and pull the chosen model(s).
3. Install and start the WinSW backend service.
4. Open the local web setup wizard at `http://127.0.0.1:8787/setup`.

Fresh installs bind to loopback and do not open a Windows Firewall LAN rule.
First-run setup requires the one-time setup token stored in
`%ProgramData%\GuardianNode\keys\setup_token.json`; the Start Menu includes a
helper shortcut to display it. LAN access should be enabled only after an
authenticated parent completes setup.

## Linux Server Installer

`installer/server-linux/install.sh`:

1. Detects the distro and installs Python, SQLite, Tesseract, Git, curl, and Avahi packages.
2. Creates a `guardiannode` system user and `/var/lib/guardiannode`.
3. Creates a root/service-user-only one-time setup token.
4. Installs the backend into `/opt/guardiannode/venv`.
5. Probes hardware, pulls Ollama models unless disabled, and writes systemd.
6. Starts `guardiannode-backend.service` and prints the local URL plus setup token.

Fresh Linux installs bind to `127.0.0.1` and set `GUARDIANNODE_MDNS_ENABLED=false`.
Do not expose the service on a LAN until after first-run setup is complete.

Docker Compose follows the same safety posture: the published port is bound to
`127.0.0.1` by default.

## Discovery

mDNS is advisory only in this alpha. A child device must be configured with an
explicit parent server URL because mDNS advertisements do not authenticate the
server. Future enrollment should pin a server public key or certificate
fingerprint together with a one-time enrollment secret.

## Service Naming

Installed services use GuardianNode-branded names:
`GuardianNodeBackend`, `GuardianNodeWatchdog`, and `GuardianNodeWatchdog2`.
Transparent naming is intentional; tamper resistance comes from Windows
permissions, not hiding process names.
