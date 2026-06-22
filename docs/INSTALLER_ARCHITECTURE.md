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
5. Install the endpoint broker, agent, tray, watchdog services, optional backend, and scheduled logon tasks.
6. Open the dashboard only when the installer knows the dashboard URL.

The agent and tray run in the signed-in Windows user session because service
session 0 cannot capture the desktop. The GuardianNode Endpoint Broker runs as
a service and is intended to own device credentials, queue state, pause state,
and backend upload transport. Watchdog services are resilience helpers.

The alpha does not ship a tested password-gated uninstaller wrapper. Uninstall
protection relies on normal Windows administrator/UAC permissions plus service
ACLs; do not describe uninstall as password-gated until a clean-machine Windows
test proves that end-to-end path.

## Windows ProgramData ACL Matrix

Target ACLs for clean-machine testing:

| Path | Contents | Intended access |
|---|---|---|
| `%ProgramData%\GuardianNode\keys\setup_token.json` | One-time setup token | SYSTEM + Administrators only; the server shortcut self-elevates before display |
| `%ProgramData%\GuardianNode\keys\device_bootstrap_token.json` | One-time local device enrollment token | SYSTEM + Administrators create; current alpha agent reads during all-in-one enrollment only |
| `%ProgramData%\GuardianNode\keys\master.key.dpapi` | DPAPI-wrapped evidence encryption key for new Windows backend installs | SYSTEM + Administrators only; machine-bound, so create a portable key backup before migration |
| `%ProgramData%\GuardianNode\keys\master.key` | Legacy/raw evidence encryption key for migrated alpha installs | SYSTEM + Administrators only; remove only after a verified portable key backup |
| `%ProgramData%\GuardianNode\evidence\` | Encrypted evidence blobs | SYSTEM + Administrators only |
| `%ProgramData%\GuardianNode\server.env` | Backend service configuration | SYSTEM + Administrators modify |
| `%ProgramData%\GuardianNode\agent.yaml` | Child capture configuration | Administrators modify; interactive users read non-secret capture settings |
| `%ProgramData%\GuardianNode\pending_pairing.json` | Installer-to-broker enrollment handoff | Administrators create; broker reads and deletes |
| `%ProgramData%\GuardianNode\Secure\device.json` | Device bearer token and backend URL | Broker-owned target storage; SYSTEM + Administrators only after Windows ACL qualification |
| `%ProgramData%\GuardianNode\device.json` | Legacy device credential from older alpha installs | Broker migration source only; not the intended current authority |
| `%ProgramData%\GuardianNode\Secure\pause_state.json` | Authoritative pause state in broker mode | Broker-owned target storage; SYSTEM + Administrators only after Windows ACL qualification |
| `%ProgramData%\GuardianNode\paused_until` | Legacy local pause marker | Compatibility fallback only; not acceptable for a qualified installer release |
| `%ProgramData%\GuardianNode\AgentSecure\queue.sqlite` and `queue.key` | Durable upload queue | Broker-owned target storage; SYSTEM + Administrators only after Windows ACL qualification |
| `%ProgramData%\GuardianNode\logs\` | Agent/tray/backend logs | Service/agent append; Administrators read |

The current architecture introduces the `GuardianNodeBroker` service so the
interactive capture helper no longer needs to own the backend bearer token or
durable queue. This remains an installer no-go until clean Windows 10/11 tests
confirm the named-pipe ACLs, ProgramData ACLs, standard-user behavior,
upgrade/repair/uninstall, and multi-session operation.

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
helper shortcut to display it. For this alpha, LAN access is a manual
administrator change after first-run setup, not a dashboard workflow.

All-in-one device enrollment uses a separate
`%ProgramData%\GuardianNode\keys\device_bootstrap_token.json` against
`POST /api/devices/bootstrap-local`. The administrator setup token must never
be copied into `pending_pairing.json` or sent to a device-pairing endpoint.

Both the server-only and all-in-one Windows installers write
`%ProgramData%\GuardianNode\server.env` through the shared
`installer/shared/server_env_windows.iss` helper before the backend service is
started. That file records the detected classifier tier, text/vision model
names, local Ollama URLs for each role, classifier timeout/context/image
settings, loopback bind settings, and non-secret runtime defaults.

## Linux Server Installer

`installer/server-linux/install.sh`:

1. Detects the distro and installs Python, SQLite, Tesseract, Git, curl, and Avahi packages.
2. Creates a `guardiannode` system user and `/var/lib/guardiannode`.
3. Creates a root/service-user-only one-time setup token.
4. Stages the source tree under `/opt/guardiannode/staging`, normalizing both
   flat archives and GitHub-style archives with one top-level directory.
5. Validates required source files and builds a staged virtualenv before moving
   the live `/opt/guardiannode/src` or `/opt/guardiannode/venv` trees.
6. Moves the previous source/venv into archived directories only after staged
   validation succeeds, and rolls back those trees if the new backend fails its
   health check.
7. Probes hardware, pulls Ollama models unless disabled, writes systemd, starts
   `guardiannode-backend.service`, and prints the local URL plus setup token.

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
`GuardianNodeBackend`, `GuardianNodeBroker`, `GuardianNodeWatchdog`, and
`GuardianNodeWatchdog2`.
Transparent naming is intentional; tamper resistance comes from Windows
permissions, not hiding process names.
