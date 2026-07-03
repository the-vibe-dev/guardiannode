# Windows 11 Alpha Installer Validation

Release target: GuardianNode 0.1.0-alpha.1 public alpha for technical parents
and early evaluators.

This page records the Windows installer evidence needed before publishing
installer artifacts. It is intentionally practical: the alpha bar is not
consumer polish, but the installers must be traceable, stoppable, uninstallable,
local-first by default, and able to produce a verified detection event after
install.

## Release artifacts

| Installer | Architecture | SHA-256 | Signed? | Required before release? | Status |
|---|---|---|---|---|---|
| `GuardianNodeChildSetup-0.1.0-alpha.1.exe` | Windows x64-compatible | `b271dd24c448ac8c333f5c86548cac2d12c35a41c48de7193d62f376becb1fb7` | No | Yes | Passed manual alpha validation |
| `GuardianNodeServerSetup-0.1.0-alpha.1.exe` | Windows x64-compatible | `92314f7613341bd2ba47c34d96131f44e63126ef7cacd248f59642604fcf954f` | No | Yes | Passed manual alpha validation |

Build commit: `41b029f64cd79ccc09f9a58c66cd124e7b6991cb`.

Unsigned alpha installers may trigger SmartScreen, Defender, or antivirus
warnings. Release notes must say this plainly and include checksums.

## Installer behavior

| Area | Child/all-in-one installer | Server installer |
|---|---|---|
| Admin rights | Required | Required |
| App files | `C:\Program Files\GuardianNode` | `C:\Program Files\GuardianNodeServer` |
| Data/config | `C:\ProgramData\GuardianNode` | `C:\ProgramData\GuardianNode` |
| Logs | `C:\ProgramData\GuardianNode\logs` | `C:\ProgramData\GuardianNode\logs` |
| Backend service | Installed only in all-in-one mode | Installed |
| Broker service | Installed | Not installed |
| Watchdog service | Installed | Not installed |
| Agent startup | All-user scheduled task `GuardianNodeAgent` | Not applicable |
| Tray startup | All-user scheduled task `GuardianNodeTray` | Not applicable |
| Firewall change | None by default | Private-profile TCP 8787 rule only when LAN/VPN mode is explicitly selected |
| Default network binding | `127.0.0.1` in all-in-one mode | `127.0.0.1` unless private LAN/VPN mode is explicitly selected |
| LAN mode | Child-only mode requires explicit server URL and pairing code | Explicit wizard choice or silent `/LAN=1 /SERVERHOST=...` |
| Stop path | Tray pause, dashboard pause, or admin uninstall | Start Menu `Stop service` shortcut |
| Uninstall path | Windows Settings / Programs & Features | Windows Settings / Programs & Features |

## Tested modes

| Mode | Platform evidence | Result | Notes |
|---|---|---|---|
| Single-node Windows with GPU | Windows 11 GPU host, RTX 3060 12 GB | Passed | All-in-one install, vision tier, pipeline health full, alert created from deterministic `notepad.exe` text event |
| Single-node Windows without GPU | Windows 11 no-GPU host | Passed | All-in-one install, text-only tier, Tesseract available, expected reduced protection warning, alert created |
| Windows server + Windows child | Windows 11 GPU server plus Windows 11 no-GPU child | Passed | Server LAN mode wrote `GUARDIANNODE_BIND_HOST=0.0.0.0`, exact allowed hosts, private firewall rule; child-only install paired and uploaded event |
| Linux GPU server + Windows child | Native Linux GPU server plus Windows 11 no-GPU child | Passed | Linux server bound to trusted LAN with explicit allowed hosts; child-only Windows install paired and uploaded event |

## Detection evidence

| Mode | Detection result |
|---|---|
| Windows GPU standalone | Alert created after installed-device event using `notepad.exe` context; vision tier and Tesseract available |
| Windows no-GPU standalone | Alert created after installed-device event using `notepad.exe` context; text-only tier and Tesseract available |
| Windows/Windows split | Alert created on Windows server from paired Windows child |
| Linux/Windows split | Alert created on Linux server from paired Windows child |

SSH-driven GUI Notepad foreground capture is not reliable enough for release
evidence because the remote session can capture the desktop or another window.
The final validation used installed device credentials and `notepad.exe` app
context events to verify the backend authentication, ingest, classification, and
alert path after installer-based install.

## Uninstall and cleanup evidence

The Windows installers define uninstall actions for services and scheduled
tasks:

- stop/uninstall `GuardianNodeWatchdog`
- stop/uninstall legacy `GuardianNodeWatchdog2` and `EndpointHealthAgent`
- end/delete `GuardianNodeAgent`
- end/delete `GuardianNodeTray`
- end/delete `GuardianNodeOllama`
- stop/uninstall `GuardianNodeBroker`
- stop/uninstall `GuardianNodeBackend`
- terminate agent, tray, and broker processes

Data under `C:\ProgramData\GuardianNode` may be retained so parents can back up
keys, logs, and evidence intentionally. Public docs must state this retention.

## Maintainer evidence to attach or archive

For each installer and mode, keep this evidence with the release record:

| Evidence item | Required? | Status |
|---|---|---|
| Installer filename | Yes | Recorded above |
| SHA-256 | Yes | Recorded above |
| Build commit SHA | Yes | Recorded above |
| Build workflow/run ID, if built in CI | Preferred | Maintainer should attach when using CI-built assets |
| Windows edition/version/build | Yes | Maintainer should attach exact `winver` or `systeminfo` output |
| CPU architecture | Yes | x64-compatible installer; attach host architecture output |
| Fresh install result | Yes | Passed in manual alpha matrix |
| Upgrade install result | If claiming upgrade support | Not claimed as supported alpha path |
| Repair install result | If claiming repair support | Not claimed as supported alpha path |
| Uninstall result | Yes | Installer scripts define cleanup; attach manual log/screenshot for release archive |
| Reinstall after uninstall result | Preferred | Passed during remote clean-install cycles; attach release archive evidence |
| Reboot persistence result | Yes, for scheduled agent/tray and services | Passed in maintainer/manual matrix; attach release archive evidence |
| Detection after install | Yes | Passed |
| Detection after reboot | Yes | Passed in maintainer/manual matrix; attach release archive evidence |
| Detection after upgrade | If claiming upgrade support | Not claimed as supported alpha path |
| Logs location verified | Yes | `C:\ProgramData\GuardianNode\logs` |
| Stop/disable instructions verified | Yes | Documented |
| Uninstall cleanup verified | Yes | Documented; attach release archive evidence |
| Defender/SmartScreen behavior observed | Yes | Unsigned warning expected; exact observed result should be recorded per asset |
| Code signing status | Yes | Unsigned |

## Pass/fail summary

| Release gate | Status | Notes |
|---|---|---|
| Exact artifact traceability | Pass | Commit and SHA-256 recorded |
| Local-first default | Pass | Loopback by default; LAN mode explicit |
| LAN/public bind warning | Pass | Docs and release notes warn; runtime settings warn when bound beyond loopback |
| Installer can be stopped | Pass | Server shortcut and tray/dashboard pause paths documented |
| Installer can be uninstalled | Pass | Windows uninstall plus manual cleanup documented |
| Detection path after install | Pass | Verified in all intended alpha modes |
| Signed installer | Non-blocking alpha issue | Unsigned; release notes must disclose |
| SmartScreen reputation | Non-blocking alpha issue | Warning expected for unsigned alpha artifacts |
