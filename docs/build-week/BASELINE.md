# Build Week Baseline

## Cutoff and repository evidence

The official cutoff is **2026-07-13 00:00 America/New_York**. The latest commit
reachable from `main` and `origin/main` before that time was:

| Evidence | Value |
|---|---|
| Baseline commit | `36b2a547056d40eff32f00aa59b7820f7d3e98d5` |
| Author/committer time | `2026-07-12T22:41:16-04:00` |
| Subject | `feat: enforce administrative step-up authentication` |
| Baseline tag | `pre-build-week-2026` |
| Build Week branch | `build-week/guardian-review` |
| Branch starting commit | `36b2a547056d40eff32f00aa59b7820f7d3e98d5` |
| Existing version | `0.1.0-alpha.1` |
| Remote | `https://github.com/the-vibe-dev/guardiannode.git` |

The working tree had no tracked modifications. It did contain unrelated,
untracked WordPress compression/validation archives and scripts. They could not
be attributed to GuardianNode from repository evidence and were not moved,
deleted, staged, or included in the baseline commit. Because they are already
untracked, no claim is made about when their content was produced.

Existing refs also included `agent/beta-release-hardening` at
`282e00a87c33c74cb249f8289c93f0122600c752` and the prior release tag
`v0.1.0-alpha.1`, which peels to
`6ce29460932826d52afb569eb464e52f81439962`.

## Existing release

GitHub already hosted the public prerelease `v0.1.0-alpha.1`, published July 4,
2026, with a checksum manifest, Windows child and server installers, and a Linux
server installer archive. The Windows executables are approximately 49.7 MB and
31.7 MB; the Linux archive is approximately 23.8 KB. Local ignored installer
build outputs also existed and are not repository source.

## Existing modules

At the cutoff, 448 files were tracked. The principal source areas were:

| Area | Tracked files | Existing role |
|---|---:|---|
| `backend/` | 204 | FastAPI API, workers, detection, persistence, evidence, auth, audit |
| `docs/` | 53 | Parent, developer, safety, deployment, and release documentation |
| `agent-windows/` | 44 | Windows capture, queue, pairing, health, watchdog, and tray |
| `dashboard/` | 38 | React/Vite parent dashboard |
| `installer/` | 28 | Windows and Linux deployment assets |
| `assets/` | 16 | Branding and release assets |
| `tests/` | 14 | Repository, release, benchmark, and synthetic E2E checks |
| `shared/` | 12 | Shared schemas, constants, and Python types |

## Existing features before Build Week

### GuardianNode agent

- Visible Windows screenshot capture with application/window context.
- Durable local frame queue, idempotent upload, retry, heartbeat, and pairing.
- Broker/watchdog services, tray/status experience, and hardware probing.

### Backend and local detection

- FastAPI backend with SQLite/Alembic persistence and background workers.
- Tesseract OCR, deterministic safety rules, and optional local Ollama
  text/vision classifiers.
- Canonical category normalization, policy evaluation, alert deduplication,
  notifications, offline monitoring, and classifier readiness status.

### Dashboard and UI

- Setup/login, dashboard health, devices, profiles, privacy policy, risk feed,
  alert details, encrypted screenshot reveal, model status, settings, and audit.
- Existing alert review and parent feedback controls. These are general alert
  controls, not Guardian Review result feedback.

### Evidence handling

- AES-256-GCM encrypted evidence blobs, protected key handling, DPAPI wrapping
  on new Windows installations, audit-on-view, retention, wipe, encrypted
  export, backup, and recovery paths.

### Installer and deployment

- Windows all-in-one, server-only, and child-only Inno Setup paths.
- Linux server installer, Docker Compose, release checksums, repair/rollback,
  uninstall, and qualification documentation.

### Authentication and security controls

- One-time setup token, parent password login, server-side sessions, idle and
  absolute session expiry, CSRF protection, recent and critical step-up auth.
- Recovery code, device bearer tokens, secure host validation, rate limiting,
  webhook restrictions, security headers, audit logging, and repository
  governance checks.

## Existing tests at the cutoff

The complete practical suite was run on the untouched baseline before Guardian
Review implementation:

| Suite | Command | Result | Test time | Wall time |
|---|---|---:|---:|---:|
| Backend | `cd backend && .venv/bin/pytest -q` | 224 passed | 46.64 s | 51.12 s |
| Windows agent | `cd agent-windows && ../.venv/bin/pytest -q` | 59 passed | 6.34 s | 8.88 s |
| Repository/E2E | `.venv/bin/pytest -q tests tests/e2e` | 58 passed | 8.82 s | 11.52 s |
| Dashboard | `cd dashboard && npm test -- --run` | 12 passed | 13.24 s | 20.31 s |

**Unique total: 353 passed, 0 failed, 0 skipped.** The E2E directory is already
included by the root invocation, so it is not counted twice.

Additional passing checks included dashboard typecheck/build, Python compile,
Ruff, backend mypy, feature/version/hardware synchronization, third-party
notices, repository controls, Linux shell syntax, strict MkDocs, actionlint,
the 196-case deterministic benchmark, backend/agent dependency audits, npm
production audit, and the Docker OCR-to-alert canary.

The baseline emitted one existing Starlette/httpx deprecation warning. No test
failure was silently repaired. Windows-only bundle and installer gates were not
runnable in this Linux environment and remain covered only by the existing July
9 qualification evidence.

Environment: Kali Linux rolling 2025.4 x86_64, kernel 6.16.8; Python 3.13.9 in
the root environment, Python 3.12.13 in the backend environment; Node 22.22.2,
npm 9.2.0; Tesseract 5.5.0; Docker 28.5.2; Git 2.53. The dashboard passed under
Node 22, while repository support documentation continues to require Node 24.

## Existing screenshots and assisted work

Tracked `assets/1.png` through `assets/6.png` are branding boards covering
brand essence, typography, colors, horizontal logo, application icon, and
vertical logo. No dashboard screenshot was found. The verifiable current UI
state is therefore the dashboard source and committed production bundle.

The repository owner identifies the existing dashboard/visual UI as
Claude-assisted and the agent/backend/security/installer/platform work as
Codex-built. Git contains one Claude-coauthored hardening commit, but does not
contain consistent assistant metadata sufficient to verify the entire split.
This attribution is recorded as owner-supplied rather than inferred fact.

## Existing known limitations

- Alpha detection can miss risks and produce false positives.
- OCR and local-model quality varies with hardware and visible content.
- Screenshots can contain highly sensitive family data.
- Windows 11 x64 is the promoted alpha client path; Windows 10 is not promoted.
- Separated deployments require a trusted VPN/TLS design; built-in mTLS is
  planned and raw public-internet exposure is unsupported.
- Binaries are unsigned and may trigger reputation or antivirus warnings.
- Current Windows 11 smoke, Windows 10 qualification, and suspend/resume gates
  remain incomplete after the July 9 lab run.
- GuardianNode is not an emergency service, a comprehensive content-control
  product, or a substitute for parent-child communication or professional help.

## Added during Build Week

The baseline tag/branch, evidence documents, submission audit corrections,
README disclosure, and Guardian Review schema contract were added after the
cutoff. The Guardian Review service and GPT-5.6 runtime were not present in the
baseline and are not claimed as implemented by these documents.
