# Beta Hardening Source Validation — 2026-08-17

This is source-level validation evidence for the implementation of
`GUARDIANNODE_REVIEW.md`. It is not Windows installer qualification, field
validation, a legal opinion, or an independent security assessment.

## Identity and environment

| Item | Value |
|---|---|
| Base commit | `0ce0fbeb15646ff31a735203ca8cedd8ee580ac2` plus the uncommitted review implementation working tree |
| Validation time | 2026-08-17 UTC |
| Host | Kali Linux x86-64, kernel 7.0.12 |
| Backend Python | 3.12.13 |
| Agent Python | 3.13.14 |
| Node/npm | 24.18.0 / 11.16.0 |
| Browser runner | Playwright Chromium desktop 1440×1000 and mobile 390×844 |

## Automated results

| Area | Command family | Result |
|---|---|---|
| Backend behavior | compileall, pytest | 292 passed |
| Synthetic API E2E | `pytest tests/e2e` | 1 passed |
| Backend static analysis | Ruff, mypy | Passed; 87 source files typed |
| Windows agent | compileall, pytest, Ruff | 67 passed; lint passed |
| Dashboard unit/static | TypeScript, Vitest, Vite | Typecheck passed; 19 passed; production build passed |
| Dashboard browser | Playwright + axe | 6 passed across desktop/mobile; no captured page/console errors or serious/critical violations |
| Root controls | pytest | 62 passed; one third-party TestClient deprecation warning in the root tooling environment |
| Rules benchmark | frozen beta-1 corpus | 196 cases; precision, recall, critical recall, and category recall 1.0; p95 0.096 ms on this host |
| Dependency audit | pip-audit and npm audit | No known vulnerabilities after `cryptography` 50.0.0 lock update |
| Packaging/config syntax | Bash, Docker Compose, PowerShell AST | Passed |
| Documentation | MkDocs strict build | Passed after link validation |

The browser test harness mocked authenticated family data and exercised Home,
Alerts, Children, Devices, Requests, Privacy & consent, Settings, and Alert
Detail. Pairing assertions cover the exact HTTPS URL, CA check words, expiring
code, and downloadable trust bundle. Browser screenshots were inspected at
native viewport sizes; temporary screenshots/traces were not added to the repo.

## Security finding remediation status

The 12 findings recorded in `GUARDIANNODE_REVIEW.md` have source changes and
regression coverage in four groups: authenticated/bounded broker IPC; cheap and
fair ingest admission; authenticated/bounded recovery activation; and durable
truthful deletion. The dependency audits also identified and prompted an update
from vulnerable `cryptography` 49.0.0 to 50.0.0 during this run.

This status means “implemented and source-tested.” Broker ACLs, session launch,
installer ordering, certificate-store behavior, signer checks, service recovery,
and capture continuity still require a real Windows host.

## Manual/external gates: not performed

- Inno Setup and PyInstaller artifact build/signing (Inno compiler unavailable).
- Exact-artifact Windows 11 clean install, reboot, standard-user, multi-session,
  sleep/wake, RDP, upgrade, repair, uninstall, and reinstall matrix.
- Independent penetration/security retest.
- Counsel/privacy review.
- Consenting family pilot and real-field accuracy/calibration results.
- Operational backup/restore and deletion drills.
- Live external Guardian Review provider evaluation.

No release should cite this document as evidence for any unchecked item. Follow
the release checklist, pilot protocol, and drill runbook and record their
credential-scrubbed evidence separately.
