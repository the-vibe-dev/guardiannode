# Roadmap

## v0.1 (Beta) — current

- ✅ Repo scaffold, license, docs
- ✅ Shared schemas (JSON Schema + Pydantic)
- ✅ FastAPI backend with encryption, redaction, rules engine, Ollama text classifier, vision classifier, multimodal merge
- ✅ SQLite + Alembic migrations
- ✅ Windows agent (Python source — process/window detection, screenshot capture + perceptual-hash dedup, redaction, tray, watchdog)
- ✅ Screenshot-based collection with server-side OCR (replaced the earlier MV3 browser extension, now removed)
- ✅ Dashboard (React + Vite + Tailwind) — login, dashboard, devices, risk feed, alert detail, settings
- ✅ Linux server installer: `install.sh` + systemd + Docker Compose
- ✅ Windows server installer (Inno Setup)
- ✅ Windows child-device installer (Inno Setup) with anti-tamper + custom uninstaller
- ✅ mDNS auto-discovery for separated mode
- ✅ Wine-based cross-build for Windows installers on Linux
- ✅ GitHub release workflow

## v0.2 — Hardening + real-world testing

- [ ] First wave of family beta testers (10–20 households)
- [ ] False-positive / false-negative tracking dashboard
- [ ] Improved redaction patterns based on beta feedback
- [ ] OCR region tuning for current Roblox, Discord, Minecraft UIs
- [ ] Better on-screen-text coverage for TikTok, Snapchat web (where possible), Instagram web
- [ ] SignPath.io OSS code-signing application
- [ ] Submit to `winget-pkgs` and Chocolatey

## v0.3 — Enforcement

- [ ] Soft pause/kill for monitored apps after critical alerts
- [ ] Hosts-file domain block with parent approval flow
- [ ] Pi-hole integration
- [ ] AdGuard Home integration
- [ ] Time-of-day policy support
- [ ] Per-child profile policy overrides

## v0.4 — Notifications

- [ ] Polished SMTP email templates
- [ ] Daily digest by severity
- [ ] Optional webhook integration (Discord/Slack/Gotify/ntfy.sh — all parent-controlled endpoints)
- [ ] Windows toast notifications on parent PC

## v0.5 — Mobile companion (read-only)

- [ ] PWA dashboard that works well on phones over LAN
- [ ] Optional push notifications via ntfy.sh self-hosted

## v1.0 — General availability

- [ ] All MVP definition-of-done items complete (full install/pair/alert/review flow verified on clean machines)
- [ ] EV code-signing certificate (sponsored or community-funded)
- [ ] First-time-user onboarding wizard in dashboard
- [ ] Polished parent-facing documentation including printable quickstart card
- [ ] Translations: Spanish, French, German, Brazilian Portuguese
- [ ] Security audit (external, public report)

## Post-1.0 ideas (not committed)

- Kernel-mode driver for stronger tamper resistance (gated on EV cert)
- macOS agent (if there's beta demand)
- Linux child-side agent (uncommon use case, but feasible)
- Federated rule/category sharing among consenting deployments (without data sharing)
- Detection-quality benchmarks against synthetic and academic corpora
- Plugin SDK for community-built extractors and classifiers
- Per-platform "trust score" so parents see at a glance how well GuardianNode covers each game/app
- A "school counselor mode" that ships a heavily restricted dashboard for use *with* (not by) social workers in foster-care contexts — gated on explicit policy framework + legal review

## What we'll never add

- Cloud telemetry on by default
- Stealth/hidden agent mode
- System-wide raw keystroke capture
- CSAM scanning (defer to law enforcement infrastructure)
- Monitoring of adults without their explicit consent
- A paid tier that gates safety features

## How to influence the roadmap

- Real-world reports via `safety_concern` issues weight heavily.
- PRs ship if they meet the criteria in `CONTRIBUTING.md`.
- For larger features, open a discussion before writing code.
