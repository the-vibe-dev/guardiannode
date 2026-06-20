# Installer Architecture

## Three installers, one repo

| Installer | Target | Tech | Output |
|---|---|---|---|
| **Child Device (Windows)** | Kid's Windows 10/11 PC | Inno Setup 6 + PyInstaller bundle | `GuardianNodeChildSetup-0.1.0-alpha.1.exe` |
| **Server (Windows)** | Parent's Windows server PC | Inno Setup 6 + PyInstaller bundle | `GuardianNodeServerSetup-0.1.0-alpha.1.exe` |
| **Server (Linux)** | Parent's Linux server PC | Shell script + systemd / Docker | `install.sh` + Docker Compose |

## Build pipeline

Cross-build from Linux using Wine + Inno Setup CLI. See [`installer/build/build_all.sh`](https://github.com/the-vibe-dev/guardiannode/blob/main/installer/build/build_all.sh).

```
Linux dev machine
   │
   ├── PyInstaller bundles agent / backend Python → dist/
   ├── Vite builds dashboard → dashboard/dist/
   ├── Inno Setup compiler (iscc.exe under Wine) consumes .iss scripts
   └── Outputs three .exe files into installer/build/dist/
```

## Child Device installer flow

```
Page 1: Welcome + privacy summary
Page 2: Choose mode (All-in-one / Connect to existing server)
Page 3: Child profile (display name + age group)
Page 4: Server connection + pairing code — only if separated
Page 5: Hardware detection + model preset — only if all-in-one
Page 6: Install + progress
Page 7: Dashboard link
```

Pascal scripts in `installer/child-device-windows/wizard_pages.iss` implement the custom pages on top of Inno Setup's wizard framework.

At install time, the child installer writes `agent.yaml`, completes or stages
pairing credentials, installs service/watchdog backstops, adds Start Menu
entries, registers all-user logon tasks for `GuardianNodeAgent.exe` and
`GuardianNodeTray.exe`, pins the tray shortcut when Windows allows it, and starts
the interactive agent/tray as the original installing user.

Desktop capture runs from the user session, not from service session 0. The
service is a resilience component; the agent that screenshots the visible
desktop must run after each Windows account signs in.

## Anti-tamper components

| Component | File | Action at install time |
|---|---|---|
| Service ACL hardening | `anti_tamper.iss` | `sc sdset` denies SERVICE_STOP to non-admin |
| Watchdog service | `anti_tamper.iss` | Registers second service that polls agent and restarts on death |
| Custom uninstaller | `custom_uninstaller.iss` | Replaces Programs & Features hook with password-gated wrapper |
| Filesystem ACL | `anti_tamper.iss` | `icacls` restricts install dir writes to SYSTEM/Administrators |

## Server installer flow (Windows)

```
Page 1: Welcome
Page 2: Hardware detect → model preset
Page 3: Admin account (password + recovery code)
Page 4: Encryption key generation (shown once)
Page 5: Network mode (loopback / LAN)
Page 6: Ollama install (silent OllamaSetup.exe) + model pull
Page 7: Backend service install (WinSW)
Page 8: Done — dashboard URL + QR code
```

## Server installer flow (Linux)

`install.sh` is a one-shot bash script:
1. Distro detection (apt / dnf / pacman / zypper)
2. Install system dependencies (python3, python3-venv, sqlite3)
3. Install Ollama via its upstream installer
4. Create `guardiannode` system user
5. Install Python venv + backend to `/opt/guardiannode/`
6. Register `guardiannode-backend.service` systemd unit
7. Start service, then print the URL to the web-based first-run wizard

Docker Compose is the alternative path; it's identical in outcome but doesn't require root on the host.

## mDNS / Zeroconf in the installers

- **Server installers** start a `_guardiannode._tcp.local` advertiser as part of the backend service. The TXT record contains the API version and the pairing-endpoint path.
- **Child Device installer** runs an mDNS *browser* on wizard page 5 if the parent chose separated mode. Discovered servers are shown in a list with their hostname; the parent picks one.
- **Fallback** if the network blocks mDNS (some segmented Wi-Fi setups do): the wizard offers a "Type the address manually" link that opens a panel for URL + pairing-code entry.

This is the "search the network" UX the parent expects without typing IP addresses.

## Wine + Inno Setup build

Inno Setup is a Windows tool but its CLI compiler `iscc.exe` runs reliably under Wine. The build script:

1. Downloads Inno Setup 6 installer (cached in `installer/build/innosetup-6.x.x.exe`).
2. Silently installs it into a project-local Wine prefix (`installer/build/.wine/`).
3. Runs `wine iscc.exe child.iss` and `wine iscc.exe server.iss`.
4. Copies output `.exe` files into `installer/build/dist/`.

The Wine path is for **local developer iteration only**. Release artifacts are
built by `.github/workflows/release-installers.yml` on `windows-latest`:
PyInstaller bundles for the backend (`GuardianNodeBackend.exe`) and agent
(`GuardianNodeAgent/Tray/Watchdog.exe`) are built natively, then Inno Setup
compiles the installers around them, generates `SHA256SUMS` plus a release
manifest, and attaches everything to a draft GitHub release.

### Fail-closed build modes

`installer/build/build_all.sh` refuses to silently ship development stubs:

| Mode | Behavior |
|---|---|
| `RELEASE_BUILD=1` | Fails the build unless real PyInstaller bundles exist at `installer/build/prebuilt/{agent,backend}`. Release installers must never require Python on a parent or child machine. |
| `ALLOW_DEV_STUBS=1` | Stages Python source + `.bat` shims (target machine needs Python). Local dev only — never distribute. |
| neither | Aborts with instructions. |

Third-party build tools (Inno Setup, WinSW) are verified against pinned
SHA-256 hashes before use, in both the script and the CI workflow.

### Service naming (transparency)

Every installed service is GuardianNode-branded: `GuardianNodeBackend`,
`GuardianNodeWatchdog`, and `GuardianNodeWatchdog2` (the secondary watchdog of
the mutual-resurrection pair). Earlier builds named the secondary watchdog
`EndpointHealthAgent`; that deceptive generic name has been removed (installer
upgrades delete the legacy service). Tamper resistance comes from the service
ACL — stopping requires admin rights — not from hiding what the service is.

## Signing roadmap

v1 ships unsigned. The plan to address SmartScreen friction is in [`installer/shared/SIGNING_PLAN.md`](https://github.com/the-vibe-dev/guardiannode/blob/main/installer/shared/SIGNING_PLAN.md).

Steps for parents until v1.1: [`docs/PARENT_GUIDES/when-windows-says-protected-your-pc.md`](PARENT_GUIDES/when-windows-says-protected-your-pc.md).
