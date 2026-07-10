# Windows Beta Qualification — 2026-07-09

This report records clean-machine Windows qualification of the beta-hardening
branch. Functional beta qualification passed. Public distribution remains
conditional on signing and release-artifact reputation checks.

## Systems

| Role | System | Relevant hardware |
|---|---|---|
| Windows clean-install target | `wingpu` / Windows 11 `10.0.22000` | NVIDIA RTX 3060, 12 GB VRAM |
| Separated parent server | `staging-backend` | NVIDIA RTX 3090, 24 GB VRAM |

The Windows bundles and both Inno Setup installers were built natively with
Python 3.12 and Inno Setup 6.7.1. Installer-source qualification ended at
`ace6377`; the frozen backend/agent payload was unchanged after `d62a25d`.

## Installation matrix

| Scenario | Result | Evidence |
|---|---|---|
| Clean all-in-one install | Pass | Backend, broker, watchdog, agent, tray, and Ollama started; `/api/health/ready` returned the current schema head and healthy workers |
| All-in-one real capture/classification | Pass | A visible synthetic self-harm/secrecy dialog produced a `critical` result and alerts using `qwen3-vl:8b-instruct` |
| All-in-one repair | Pass | Configuration, device identity, and database history survived; the installer created a pre-upgrade backup |
| Injected failed all-in-one upgrade | Pass | Installer exit `1`; prior application and device hashes restored; services restarted; readiness returned; maintenance marker cleared |
| Clean server-only install | Pass | Only the backend service was installed; private-LAN bind/allowed-host configuration and firewall rule were correct |
| Server LAN access | Pass | A separate Linux host reached `http://192.168.1.123:8787/api/health/ready` |
| Server-only repair | Pass | Exit `0`; `server.env` preserved; database, environment, and complete prior application tree backed up |
| Clean separated child install | Pass | Only broker/watchdog services and agent/tray tasks were installed; no backend or `server.env`; one-time pairing completed and was consumed |
| Remote child capture/classification | Pass | Staging received the Windows frame and classified it `critical` with `self_harm`, `secrecy_request`, and `threat` categories on the RTX 3090 |
| Child repair | Pass | Exit `0`; remote URL and protected device identity preserved; application and protected-state backup present |
| Cold reboot and logon | Pass | Delayed-auto services recovered; real RDP logon started agent/tray in session 2; post-boot heartbeat reached staging |
| Watchdog recovery | Pass | Killing the agent in an active session caused a new process to launch in the same session |
| Child uninstall | Pass | Exit `0`; services, tasks, processes, and application directory removed; user data intentionally preserved |
| Server uninstall | Pass | Exit `0`; service, application directory, firewall rule, and Ollama task removed; user data intentionally preserved |

All-in-one and child ACL qualification passed. The assertions cover protected
files/directories, low-privilege filesystem access, service DACLs, and expected
partial-install omissions.

## Classifier gates

The live 196-case text-safety benchmark ran against Ollama on the dedicated RTX
3090 and passed every beta gate:

| Metric | Result |
|---|---:|
| Cases | 196 |
| Precision | 97.48% |
| Recall | 100% |
| Critical recall | 100% |
| Category recall | 100% |
| False negatives | 0 |
| False positives | 3 |
| p95 latency | 1.56 s |

The deterministic rules benchmark also passed all 196 cases with 100%
precision, recall, critical recall, and category recall.

## Defects found and corrected

| Commit | Correction |
|---|---|
| `d62a25d` | Finalize SQLite backups as standalone files and remove temporary WAL/SHM sidecars |
| `bd23be0` | Avoid expanding `{app}` before Inno initializes it during silent setup |
| `f238d54` | Treat mode-specific ACL artifacts as optional while still checking every artifact that exists |
| `3cccbff` | Back up the prior application and protected state; restore both and return nonzero on readiness failure |
| `ace6377` | Remove WinSW-created residual logs/application directories and clean the private-LAN firewall rule |

## Repository checks

| Check | Result |
|---|---|
| Backend tests | 209 passed |
| Windows agent tests | 59 passed |
| Root/release tests | 56 passed, 1 deprecation warning |
| Dashboard | 12 tests passed; typecheck and production build passed; built output matches backend static assets |
| Documentation | Strict MkDocs build passed |
| Agent Ruff | Passed |
| Backend dependency audit | No known vulnerabilities |
| Agent dependency audit | No known vulnerabilities |
| Release helper checks | Feature matrix, versions, hardware tiers, third-party notices, repository controls, Linux installer syntax all passed |

## Disposition and remaining distribution gates

Engineering qualification for a controlled beta is **PASS**. Before publishing
the Windows executables broadly, complete these release-operations gates:

- Authenticode-sign both installers and bundled executables with the production
  certificate, then verify signatures after upload.
- Run Defender/SmartScreen and multi-engine AV checks against the exact signed
  artifacts. This clean lab intentionally validated unsigned engineering builds.
- Repeat a smaller smoke matrix on a current Windows 11 build and Windows 10;
  this run used Windows 11 build 22000.
- Exercise suspend/resume on hardware with an independently controlled wake
  path. Reboot, delayed service recovery, logon, disconnect, and watchdog
  recovery were covered here; remote suspend was not attempted because the lab
  had no guaranteed wake mechanism.

Raw, credential-scrubbed evidence is stored outside the repository at
`/mnt/nas_ai/shared/droppoints/guardiannode/20260709-beta-validation/`.
