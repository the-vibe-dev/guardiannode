# GuardianNode Public Alpha Release Readiness

## 1. Executive decision

**APPROVE PUBLIC ALPHA RELEASE**

GuardianNode is ready for a public alpha release aimed at technical parents,
developers, early evaluators, and safety reviewers. This is not an approval for
a finished consumer child-safety product, production/stable deployment, public
internet exposure, enterprise/commercial compliance use, or guaranteed child
safety claims.

## 2. Exact target

- Public alpha for technical parents and early evaluators.
- Local-first usage on parent-owned or legally administered devices/accounts.
- Windows 11 installer alpha and source release are in scope.
- Not production/stable.
- Not an ordinary non-technical family consumer release.

## 3. Tested commit and environment

Tested release-candidate code commit:
`5c027d511464ee77e246303744041c4c312d6d82`.

This report file was added after that tested code commit; it does not change
runtime behavior.

Local environment:

- Date: 2026-07-03
- OS: Linux `kalidev` 6.16.8+kali-amd64 x86_64
- Python: 3.13.9
- pip: 26.1.2 in fresh validation virtualenvs
- Node: v22.22.2
- npm: 9.2.0
- Docker: 28.5.2+dfsg3
- Docker Compose: 2.40.3-3

GitHub Actions evidence already green before this readiness commit:

- Tests: https://github.com/the-vibe-dev/guardiannode/actions/runs/28685736778
- Pages/docs deploy: https://github.com/the-vibe-dev/guardiannode/actions/runs/28685842615

Final release tagging should use the latest pushed commit after GitHub tests and
Pages are green for that commit.

## 4. Artifact matrix

| Artifact | Intended audience | Tested platform | Required before release? | Current status | Blocker? |
|---|---|---|---|---|---|
| Source archive from release tag | Developers, security reviewers, technical parents | Linux local validation and GitHub source workflows | Yes | Ready after tag | No |
| `GuardianNodeChildSetup-0.1.0-alpha.1.exe` | Windows technical parents; all-in-one or child-only | Windows 11 GPU, Windows 11 no-GPU, Windows child paired to Windows/Linux server | Yes, if Windows installers are published | Built and manually validated | No |
| `GuardianNodeServerSetup-0.1.0-alpha.1.exe` | Parent-owned Windows server PCs | Windows 11 GPU server | Yes, if Windows server installer is published | Built and manually validated | No |
| Portable zip | None | Not applicable | No | Not a supported alpha artifact | No |
| Service-mode Windows install | Technical parents/admins | Windows 11 | Yes | Backend/broker/watchdog services validated | No |
| User-session Windows agent/tray | Technical parents/admins | Windows 11 | Yes | Scheduled task startup validated | No |
| Agent-only install | Child-only Windows mode paired to parent server | Windows 11 no-GPU child | Yes | Validated | No |
| Dashboard/backend bundle | Parent dashboard users | Backend static serving, dashboard build, Docker backend | Yes | Build and static bundle diff passed | No |
| Native Linux server install | Advanced technical parents | Linux GPU server | Yes, if documented as supported source/native path | Validated manually and by installer tests | No |
| Docker/dev setup | Advanced technical evaluators | Docker Compose on Linux | No for primary Windows alpha; yes for optional technical path | Compose config, backend image build, and `/api/health` smoke passed | No |
| Documentation site | All alpha users | MkDocs strict build and Pages workflow | Yes | Passed | No |
| GitHub release notes | All alpha users | Docs/release notes tests | Yes | Ready | No |

## 5. Windows installer validation

| Installer | SHA-256 | Signing status | Status |
|---|---|---|---|
| `GuardianNodeChildSetup-0.1.0-alpha.1.exe` | `b271dd24c448ac8c333f5c86548cac2d12c35a41c48de7193d62f376becb1fb7` | Unsigned | Passed |
| `GuardianNodeServerSetup-0.1.0-alpha.1.exe` | `92314f7613341bd2ba47c34d96131f44e63126ef7cacd248f59642604fcf954f` | Unsigned | Passed |

Installer behavior:

- Architecture: Windows x64-compatible.
- Admin rights: required.
- Child/all-in-one files: `C:\Program Files\GuardianNode`.
- Server files: `C:\Program Files\GuardianNodeServer`.
- Config/data/logs: `C:\ProgramData\GuardianNode`, logs under `logs`.
- Services: backend in all-in-one/server mode; broker and watchdog on child/all-in-one.
- Startup: all-user scheduled tasks `GuardianNodeAgent` and `GuardianNodeTray`.
- Stop: server Start Menu stop shortcut; tray/dashboard pause; admin service control.
- Uninstall: Windows Settings / Programs & Features; uninstaller stops services,
  deletes scheduled tasks, and removes program files.
- Data retention: `C:\ProgramData\GuardianNode` may remain for keys/logs/evidence
  backup; documented.
- SmartScreen/Defender: unsigned alpha warning expected and documented.

Manual matrix passed:

- Windows GPU standalone: vision tier, full protection, detection/alert verified.
- Windows no-GPU standalone: text-only tier, Tesseract available, detection/alert verified.
- Windows server + Windows child: LAN mode explicit, allowed hosts/firewall rule set, pairing and detection verified.
- Linux GPU server + Windows child: Linux trusted-LAN server and Windows child pairing/detection verified.

Full evidence page:
`docs/release/windows-11-alpha-installer-validation.md`.

## 6. Test results

| Area | Command | Result |
|---|---|---|
| Root/release tests | `/tmp/gn-alpha-root-venv/bin/python -m pytest -v tests` | 50 passed, 1 skipped |
| Backend compile | `/tmp/gn-alpha-backend-venv/bin/python -m compileall -q app tests` | Pass |
| Backend tests | `/tmp/gn-alpha-backend-venv/bin/python -m pytest -v` | 203 passed, 1 warning |
| Synthetic E2E | `/tmp/gn-alpha-backend-venv/bin/python -m pytest -v ../tests/e2e` | 1 passed, 1 warning |
| Agent compile | `/tmp/gn-alpha-agent-venv/bin/python -m compileall -q src tests` | Pass |
| Agent tests | `/tmp/gn-alpha-agent-venv/bin/python -m pytest -v` | 59 passed |
| Dashboard install | `npm ci` | Pass, 0 vulnerabilities reported |
| Dashboard audit | `npm audit` | 0 vulnerabilities |
| Dashboard typecheck | `npm run typecheck` | Pass |
| Dashboard tests | `npm test -- --run` | 4 files, 12 tests passed |
| Dashboard build | `npm run build` | Pass |
| Static bundle current | `diff -qr dashboard/dist backend/app/static` | Pass |
| Docs build | `/tmp/gn-alpha-docs-venv/bin/mkdocs build --strict --site-dir /tmp/gn-alpha-site` | Pass |
| Feature matrix | `/tmp/gn-alpha-root-venv/bin/python scripts/check_feature_matrix.py` | Pass |
| Version consistency | `/tmp/gn-alpha-root-venv/bin/python scripts/check_version_consistency.py` | Pass |
| Hardware tier constants | `/tmp/gn-alpha-root-venv/bin/python scripts/sync_hardware_tiers.py --check` | Pass |
| Third-party notices | `/tmp/gn-alpha-root-venv/bin/python scripts/check_third_party_notices.py` | Pass |
| Repository controls source files | `/tmp/gn-alpha-root-venv/bin/python scripts/check_repository_controls.py` | Pass |
| Backend smoke server | Uvicorn on `127.0.0.1:8877` plus HTTP probe script | Pass |
| Docker Compose config | `docker compose -f installer/server-linux/docker-compose.yml config` | Pass |
| Docker backend build | `docker compose -f installer/server-linux/docker-compose.yml build backend` | Pass |
| Docker smoke | `docker compose ... up -d`, `curl http://127.0.0.1:8787/api/health` | Pass |

Backend smoke checks passed:

- `/api/health`
- setup incomplete status
- login rejected before setup
- CSRF token issuance
- Host-header rejection
- SPA root serving
- recovery-code setup-token flow
- first-run setup completion
- setup complete status
- authenticated `/api/auth/me`
- unauthenticated `/api/auth/me` rejection
- full setup token not logged
- clean shutdown

## 7. Security results

| Check | Command | Result | Triage |
|---|---|---|---|
| Backend Ruff | `/tmp/gn-alpha-backend-venv/bin/ruff check app tests` | Fails baseline with 164 style/framework findings | Non-blocking alpha issue; mostly FastAPI `Depends(...)` B008, import ordering, `datetime.UTC` suggestions |
| Agent Ruff | `/tmp/gn-alpha-agent-venv/bin/ruff check src tests` | Pass | No issue |
| Bandit | `/tmp/gn-alpha-backend-venv/bin/bandit -r app -ll` | No medium/high issues | Pass |
| Backend pip-audit | `/tmp/gn-alpha-backend-venv/bin/pip-audit` | No known vulnerabilities; local package skipped | Pass |
| Agent pip-audit | `/tmp/gn-alpha-agent-venv/bin/pip-audit` | No known vulnerabilities; local package skipped | Pass |
| Docs pip-audit | `/tmp/gn-alpha-docs-venv/bin/pip-audit` | No known vulnerabilities | Pass |
| npm audit | `npm audit` | 0 vulnerabilities | Pass |
| Secret scan | tracked files via `detect-secrets scan` | 31 candidates | False positives: pinned hashes, synthetic test passwords/tokens, redaction fixtures, static/docs strings |
| Artifact scan | `git ls-files` for binary/archive outputs | No tracked `.exe`, `.msi`, `.zip`, `.tar`, `.gz`, `.dll`, `.pyd`, `.so`, `.gnexport`, `node_modules`, or `dist` outputs | Pass |
| License/dependency summary | `scripts/check_third_party_notices.py` | Pass | Direct dependency notices current |
| SBOM | Not configured | Not run | Non-blocking; repo has no SBOM generation workflow |

## 8. Release-critical security behavior

Network exposure:

- Backend default bind host is `127.0.0.1`.
- Windows all-in-one/server default writes loopback config.
- Docker publishes host port as `127.0.0.1:8787:8787`.
- LAN mode is explicit in Windows server installer and Linux env vars.
- Runtime settings and startup logs warn when backend binds beyond loopback.
- Host-header validation is enabled by default; wildcard Host headers are
  dev-mode-only.
- CORS is disabled unless explicitly configured.
- CSRF protection covers browser-authenticated mutating API routes.

Authentication/setup:

- First-run setup requires a generated one-time token.
- Setup cannot be completed with a wrong/expired token.
- Token is single-use.
- Full setup token is not logged.
- Sensitive parent endpoints require auth.
- Device endpoints use device bearer credentials after pairing.

Sensitive data:

- No GuardianNode-operated cloud telemetry by default.
- Captured screenshots/OCR/events stay local to parent-controlled backend.
- Evidence blobs and event text are encrypted at rest.
- SQLite metadata is not fully encrypted; docs disclose plaintext metadata.
- SMTP/webhook notifications are parent-configured opt-in network egress.
- Public issue docs warn not to upload screenshots, messages, tokens, exports, or logs with PII.

Installer safety:

- No public network exposure by default.
- Windows firewall rule is only added in explicit private LAN/VPN server mode.
- Services/tasks are documented and uninstallable.
- Protected data paths are ACL-hardened.
- Manual cleanup path is documented.

Child-safety expectation management:

- Docs and release notes state alpha status, false positives/false negatives,
  no guaranteed child safety, no replacement for parenting/professional help, no
  public internet exposure, and authorized-device/account use only.
- Emergency guidance is present in safety-boundaries docs.

## 9. Remaining blockers

None.

## 10. Non-blocking alpha issues

- Backend Ruff baseline has style/framework findings.
- Installers are unsigned; SmartScreen/Defender warnings are expected.
- Docker is a technical self-hosting path, not the primary parent alpha path.
- GitHub repo currently reports `visibility=PRIVATE`; maintainers must make the
  repo/release public before announcing a public alpha.
- GitHub branch protection API returned 403 for the current private repo/plan;
  maintainers must confirm branch protection, required checks, secret scanning,
  Dependabot alerts, protected tags, and private vulnerability reporting.
- GitHub Discussions are disabled; Issues and private vulnerability reporting
  are the documented feedback/security paths.
- Node v22 passed locally even though README lists Node.js 24 for source setup.
- The alpha may miss risks and false-alarm; disclosed.
- No macOS/Linux child-device installer.
- No auto-update, code signing, production observability, or consumer support.

## 11. GitHub/release operations readiness

Verified locally or via `gh`:

- Default branch: `main`.
- License: AGPL-3.0.
- Issues enabled.
- Security policy present.
- CODEOWNERS present.
- Dependabot config present for GitHub Actions, backend Python, agent Python,
  dashboard npm, and Docker.
- Issue templates and pull request template present.
- Tests and Pages were green on the previous pushed main commit.

Maintainer confirmation required:

- Make repository/release public before public alpha announcement.
- Branch protection for `main`.
- Required CI checks for merge.
- Protected release tags or controlled tag process.
- Secret scanning and push protection.
- Dependabot alerts/security updates.
- Private vulnerability reporting availability.
- Whether Discussions should be enabled or Issues are the sole feedback channel.

## 12. Required release-note warnings

Release notes must include:

- Alpha software, not production/stable.
- Not guaranteed child safety.
- Not a replacement for parental involvement, professional support, or emergency services.
- Do not expose directly to the public internet.
- Use only on devices/accounts you own or are legally responsible for.
- Windows 11 tested scope.
- Installer checksums.
- Unsigned installer status and SmartScreen/Defender warning.
- Local-first privacy model and sensitive screenshot/OCR evidence warning.
- Known limitations including false positives/false negatives and text-only hardware limits.

These warnings are present in `docs/RELEASE_NOTES_0.1.0-alpha.1.md`.

## 13. Final recommendation

**APPROVE PUBLIC ALPHA RELEASE.**

The release is honest, local-first by default, testable, documented, uninstallable,
and does not claim production readiness or guaranteed child safety. There are no
concrete reproducible blockers for the stated public-alpha target.
