# Screenshot and AI review - review.4 validation

Review build: `2026-11-13-review.4`. Application: `0.1.0-alpha.3`.
This is a source evaluation package. Validation logs use UTC timestamps; the
review-build identifier preserves the existing dated package series.

## Input and integration

Authoritative input: `guardiannode-main (9).zip`.
SHA-256: `ed38682857dab6b35516107432746ea7c67ceb5a222af9f8b0d73a40d05a20af`.

The input already contains review.3. Newer dashboard dependencies, GitHub action
pins, release records, Docker Python base and the Linux installer's executable
mode are preserved. All six Python/dashboard manifests and lockfiles remain
byte-for-byte identical to the upload. No migration or published installer was
created. The historical review.3 integration record is not this pass's evidence.

## Executed checks

| Check | Current result | Evidence under `review/validation` |
|---|---|---|
| Backend/API and root synthetic E2E | 574 passed; no failures/errors/skips | `backend-e2e-tests.txt`, `backend-e2e-junit.xml` |
| Endpoint Python suite | 227 passed; no failures/errors/skips | `agent-pytest.log`, `agent-pytest.xml` |
| Repository controls and contracts | 70 passed; no failures/errors/skips | `repository-tests.txt`, `repository-junit.xml` |
| Dashboard unit/component suite | 105 passed in 21 files | `dashboard-unit.log` |
| Total across those suites | 976 passed; 86 added regression cases versus review.3 | `validation-summary.json` |
| Backend Ruff | Passed | `backend-ruff.txt` |
| Backend Mypy | Passed, 89 source files; existing exclusions remain | `backend-mypy.txt` |
| Endpoint Ruff | Passed | `agent-ruff.log` |
| Dashboard TypeScript | Passed | `dashboard-typecheck.log` |
| Production dashboard build | Passed | `dashboard-build.log` |
| Generated OpenAPI/client | 93 paths; five optional evidence-reference fields | `openapi.json`, `dashboard-handoff.json` |
| Matched compiled dashboard | 81 files, 1,753,580 bytes; SHA-256 equality with `dist` | `dashboard-static-manifest.json` |
| Rules-only corpus | 196 cases; configured gates passed | `rules-benchmark.json` |
| Dashboard dependency audit | Zero vulnerabilities reported for current lock | `dashboard-npm-audit.json` |

Mypy retains its existing error exclusions for `app.services.notifications`,
`app.services.image_safety` and `app.api.events`. Do not interpret its success as
strict checking of excluded modules. No dependency audit can prove an absence
of vulnerabilities. The deterministic corpus is a fixture regression check,
not a measure of real-world OCR or model accuracy.

## Reproduce source checks

Use the project-specific frozen environments and development dependencies.
Commands below run from the indicated directory; the logs capture this run's
results.

```sh
# backend/
uv sync --frozen --extra dev
uv run pytest -q tests ../tests/e2e
uv run ruff check app tests
uv run mypy app

# agent-windows/
uv sync --frozen --extra dev
uv run pytest -q tests
uv run ruff check src tests

# dashboard/
npm ci
npm run typecheck
npm test -- --run
npm run build

# source root, using the backend environment
backend/.venv/bin/python -m pytest -q tests --ignore=tests/e2e
backend/.venv/bin/python scripts/run_classifier_benchmark.py --mode rules
backend/.venv/bin/python scripts/check_repository_controls.py
backend/.venv/bin/python scripts/check_version_consistency.py
backend/.venv/bin/python scripts/check_build_week_submission.py --json
```

Windows uses the corresponding `.venv\Scripts\python.exe` path. The source ZIP
cannot verify Git history, a historical baseline tag, or remote repository
protection settings. Historical public submission gates remain external.

## Regression evidence

Backend before-fix tests reproduced lost text-model provenance, obscured invalid
text status, a changed active consent generation being accepted and reassignment
during OCR using stale child context. Final tests cover receipt-time assignment
binding, legacy pending compatibility, handoff and mid-processing changes, short
SQLite write reservations, stale alert decisions and recovery of a 70-frame,
two-device pending backlog across replay rounds and restart.

Endpoint regressions cover primary display enumeration, missing monitors,
negative coordinates, physical DPI coordinate consistency, focus/geometry
changes, JPEG admission, encoded dimensions, zero/max thresholds, monotonic
timing, privacy pause/resume and corrupt versus transient queue failures.

Dashboard before-fix tests reproduced deleted assessment text remaining visible
after a failed refresh and a delayed feedback response contaminating a newly
selected review. Final tests also cover stale evidence conflicts, delayed
selection/deletion responses, provider/history independence, device errors and
loading states. The before-fix logs are historical reproduction evidence, not
failed final gates.

## Local repository integration verification (2026-11-14)

The review.4 product files were integrated into `main` from the supplied ZIP.
The four suites passed locally: backend/API and synthetic E2E 574, Windows agent
227, repository tests 71, and dashboard 105 (977 tests total). The repository
count is one higher than the archive's source evaluation. Dashboard Playwright
passed 16 desktop and mobile flows. The Browser plugin was unavailable, so this
run used local Playwright against the built application.

Backend and agent Ruff, backend Mypy, dashboard TypeScript, production build,
repository governance/version/submission gates, and generated OpenAPI/client
schema comparison passed. The compiled dashboard contained 81 files and matched
both `dashboard/dist` and the supplied package byte for byte. The rules-only
196-case corpus passed its configured gates. `npm audit` reported zero known
vulnerabilities for the current dashboard lockfile.

These local checks supplement the supplied report. They do not qualify native
Windows hardware, live model performance, Docker startup, installer behavior,
or PostgreSQL concurrency.

## Runtime checks not completed in the source archive

The source evaluation's connected browser could not initialize without the originating extension
context. Vite ran on loopback, but the cloud browser could not reach the preview
and returned `net::ERR_CONNECTION_REFUSED`. No current rendered-browser or
accessibility pass is claimed. See `dashboard-browser.log`.

Native Windows services, display hardware/DPI/hot-plug/RDP, IPC, ACLs, actual
installer upgrade/uninstall, Docker startup, live OCR/local-model performance
and real external-provider delivery were not qualified here. Tests use Linux,
SQLite and synthetic data/provider responses. PostgreSQL concurrency was not
qualified. The project's alpha status remains appropriate.

## Current semantics and follow-on gaps

Newly accepted frames bind server-observed child assignment. Legacy pending
frames without that field retain compatible classification-time assignment.
Revision-aware actions are protected when `expected_risk_id` is supplied; the
matching dashboard supplies it, while older clients may omit it.

Full-screen capture still covers one primary display. App capture is a visible
window rectangle, including any overlapping pixels. Sampling, resize and JPEG
encoding can miss brief or small content. Pending work defaults to a 600-second
age policy; expired work enters bounded quarantine, whose default housekeeping
policy is seven days and 256 MiB. A crash after database commit but before
pending-file deletion can replay a frame; exactly-once processing is not claimed.

Full occurrence history, global Guardian Review pagination beyond 200 recent
rows, parent-facing quarantine replay, durable complete capture/drop telemetry,
optional pixel masking, named reviewers and qualified distribution remain
prioritized work in [the roadmap](../ROADMAP.md).

The supplied report, comparison, validation logs and package manifest are
retained in the local gitignored review archive. Package integrity and source
tests are separate from runtime qualification.
