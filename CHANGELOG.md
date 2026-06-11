# Changelog

All notable changes to GuardianNode are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it reaches
1.0.

## [Unreleased]

### Tamper resistance + tray dialog (field-test round 2)
- **Tray Exit/Pause dialog fixed**: the password box ignored typing and the
  OK/Cancel buttons didn't respond because the Tk dialog was created inside
  pystray's callback thread and never got window focus. Dialogs now render in a
  separate process (`GuardianNodeTray.exe --prompt …`) with a clean main thread.
- **Two cooperating watchdog services** for tamper resistance: the named
  `GuardianNodeWatchdog` and a second, generically-named `EndpointHealthAgent`,
  each configured with `--peer-service` so they restart each other. Both also
  re-run the agent and tray scheduled tasks if those processes are ended from
  Task Manager. The tray now runs as an all-users logon task (not a Startup
  shortcut) so it, too, can be relaunched.
- **Offline / monitoring-stopped alerts**: the backend raises a high-severity
  alert and notification when a device stops sending heartbeats for
  `device_offline_after_seconds` (default 180s), and clears it when the device
  reconnects. This is the safety net for the one thing a local-admin child can
  always do — kill everything at once or power off — which no amount of
  client-side hardening can prevent. Recommend running the child as a standard
  (non-admin) Windows user; see *What this cannot stop*.
- **Installer upgrades no longer roll back**: `PrepareToInstall` stops the
  services, scheduled tasks, and running processes before the file-copy stage,
  so in-place upgrades don't fail with "file in use".

### Fixed (post-lenovohouse field test)
- **Duplicate agent/tray instances**: the agent ran as a session-0 service *and*
  a startup shortcut *and* an install-time launch. The agent is now launched
  only by the `GuardianNodeAgent` scheduled task — registered for the
  **BUILTIN\Users group**, so it starts inside every user's session at logon
  (services cannot capture the desktop from session 0). Both agent and tray
  gained per-session single-instance mutexes, so duplicate launchers can never
  stack again. The watchdog service now watches the agent *process* across all
  sessions and re-runs the scheduled task if it is killed.
- **Tray showed a generic green dot**: the tray now loads the GuardianNode logo
  (shipped as `icon.png` next to the exe; paused state shows an amber badge),
  the placeholder 16×16 `icon.ico` was replaced with a multi-resolution brand
  icon, all shortcuts carry it, and the taskbar pin now pins the branded
  Start Menu shortcut instead of the bare exe.
- **Alert flooding**: a risky note sitting on screen produced dozens of
  identical alerts (21 in 15 minutes in the field test). Identical open
  findings (same device/profile/severity/categories) within a 30-minute window
  now fold into one alert with a repeat counter (`×N` in the Risk Feed) whose
  detail always points at the newest evidence. Escalations and reviewed alerts
  always create a fresh alert. Window configurable via
  `GUARDIANNODE_ALERT_DEDUP_WINDOW_SECONDS`.
- **Missed background changes**: a background window loading new content (e.g.
  a browser behind Notepad) never triggered a capture because the change
  detector keyed on the foreground window's hash. Whole-screen change is now an
  independent trigger (`full_screen_change_threshold`, default 10/256 bits).

### Added (post-lenovohouse field test)
- **Agent upload backlog in the dashboard**: device heartbeats now POST
  `/api/devices/heartbeat` with the agent's queued-frame count (also updating
  device liveness); the pipeline widget shows "N waiting upload" per device
  alongside the in-flight count.

### Builder notes
- Codex was the primary builder for this release train, covering the backend,
  installer, agent, documentation, release-hardening, and test work.
- Claude/Fable contributed UI polish and supporting product/documentation
  updates across the dashboard and release materials.

### Added
- **Branding applied everywhere** from the kit in `assets/`: optimized logos,
  icons, favicons, and an Open Graph card generated into `assets/brand/` (with a
  text README documenting the palette and fonts); README header with logo and
  badges plus a new System requirements section; dashboard favicon, page
  metadata, self-hosted Inter/Sora fonts (`@fontsource`, no CDN — the product
  does not phone home), and the Tailwind palette aligned to the official
  Deep Teal `#0D3B4A` / Forest Green `#275E3D`.
- **Documentation website** (MkDocs Material) with a branded landing page
  (`docs/index.md`), brand styles, og/twitter cards, and navigation over all
  parent guides and developer docs; deployed to GitHub Pages by
  `.github/workflows/deploy-docs.yml`.
- Backend SPA fallback now serves root-level static files (favicon, icons)
  directly instead of returning `index.html` for them.
- **Device pairing now works end-to-end.** The agent completes pairing at startup
  from the installer's `pending_pairing.json` drop-file (with mDNS auto-discovery
  when the server URL is blank), and a manual
  `GuardianNodeAgent.exe --pair --server <url> --code <code>` CLI was added.
  Previously the pairing client existed but nothing invoked it.
- **Loopback local-bootstrap pairing** for all-in-one installs: the first device
  on the same machine can pair without a code (loopback-only, closes permanently
  once any device is paired, audit-logged).
- **Brute-force protection**: `/api/auth/login`, `/api/auth/recovery-reset`, and
  `/api/devices/pair/complete` now lock out an IP for 15 minutes after 10 failed
  attempts (HTTP 429 + `Retry-After`).
- Risk Feed shows *what happened*: the alerts list API now includes the risk
  summary, categories, and app name; the feed displays them with friendly
  device/child names and an open-alert count.
- Devices page "Remove" action (wired to the existing revoke endpoint).
- Audit log entry (`evidence.view_text`) when decrypted event text is viewed,
  matching the existing screenshot-view auditing.

### Fixed
- **Windows all-in-one installer never started the backend** — the Backend
  service is now shipped, installed, and started before the agent so pairing and
  the dashboard work immediately after install.
- Windows installer: the Watchdog service was staged but never registered; it is
  now installed and started, and all three services get the stop-deny ACL.
- Windows installer: removed the parent-password wizard page whose input was
  silently discarded — account + recovery-code creation happens in the dashboard
  first-run wizard, and the README now describes the real flow.
- Windows installer: the child age group is now written to `agent.yaml` as a real
  `age_group` value instead of a comment.
- Linux installer: `git` was used to fetch the source but never installed;
  added it to every distro's package list.
- Dashboard overview severity cards were silently unstyled (dynamically-built
  Tailwind class names are not generated by the JIT compiler); replaced with a
  static class map.
- Alert detail Event/Classification grid no longer overflows on phone screens.
- Backend test isolation: the SQLAlchemy engine is reset per test instead of
  leaking the first test's database into the whole run.
- Generic **webhook notification channel** (ntfy/Gotify/generic), wired into alert
  dispatch and the per-channel test-send, with delivery recorded in the audit log.
- Webhook URL field in the dashboard Settings → Notifications form.
- Backend tests for retention cleanup (expired alerts/events/blobs/audit rows) and
  notification test-send (success/failure, no secret leakage).
- Dashboard JavaScript test suite (vitest — UTC timestamp normalization, responsive
  Layout/Login).
- Release-metadata docs: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md),
  [docs/REPRODUCIBLE_BUILDS.md](docs/REPRODUCIBLE_BUILDS.md).
- `SHA256SUMS` generation step in `installer/build/build_all.sh`.

### Removed
- **Browser extension** and all of its dedicated plumbing — collection is now
  screenshot-only with server-side OCR. Removed `browser-extension/`, the agent's
  loopback extension HTTP server + event queue + client-side redactor, the
  `extension_listen_port` config, and the installer's browser force-install
  registry policies / `register_browser_policy.bat`. The generic
  `POST /api/events` text-ingest API is retained.

### Fixed
- Retention cleanup never removed evidence blobs in practice: the
  `NOT IN (referenced blob ids)` query included `NULL` ids from events without a
  screenshot, and SQL `NOT IN` against a set containing `NULL` matches no rows.
  Stale, unreferenced blobs are now cleaned as intended.

### Changed
- Set the GitHub owner to `the-vibe-dev` across README, SECURITY, installers, and
  parent guides (replaced the `YOUR_ORG` placeholders).

### Notes / remaining before public release
- Code signing for Windows installers (see
  [installer/shared/SIGNING_PLAN.md](installer/shared/SIGNING_PLAN.md)).
- Pixel-level responsive verification (390/768/desktop) via a real browser
  (Playwright) — the jsdom tests guard the responsive markup but not layout.

## [0.1.0] — Beta (pre-release)

Initial proof-of-concept: Windows child agent, local FastAPI backend, React
dashboard, three-tier classifier (vision_only / full / text_only),
encrypted-at-rest evidence, parent auth + recovery, device pairing,
retention/notification/storage/audit settings, and policy + child-request APIs.
(This release also shipped an MV3 browser extension, since removed in favor of
screenshot-only collection — see Unreleased.)
