# Independent review remediation checkpoint — 2026-10-31

The local handoff archive `GuardianNode_Independent_Review_and_Agent_Handoff.zip`
was reviewed against the Git checkout that began at `656feeb` (version
`0.1.0-alpha.3`, migration head `0007_family_beta_workflows`). The handoff's
source ZIP had no Git metadata, so its archive hash is not asserted to identify
that commit. Existing untracked operator files were preserved.

## Release decision

**Engineering alpha with synthetic data only. Ordinary-family beta is blocked.**
The attached twelve regression scenarios now pass in a disposable environment,
but they cover only a subset of the 18 findings. Windows host behavior, durable
deletion under crash, multi-monitor coverage, full backend/browser journeys,
and live provider integration remain unqualified. No new installer has been
published or deployed.

## Finding ledger

| ID | Status at this checkpoint | Evidence / remaining gate |
| --- | --- | --- |
| GN-01 | Partly fixed | Shared effective policy gates capture, context, retention, notifications and external review. Verify all toggles through a packaged endpoint and real provider. |
| GN-02 | Partly fixed | Queued work is fenced and withdrawal stop is delivered through a control-only credential until broker acknowledgment. Offline, in-flight provider and repair behavior need host tests. |
| GN-03 | Partly fixed | Broker persists pause and blocks submission; real Windows pause/offline/restart matrix remains. |
| GN-04 | Fixed in SQLite tests | Feedback and notification dependents are deleted; full failure/restart matrix remains. |
| GN-05 | Fixed in focused tests | Blob-only retry preserves unexpired alert metadata. |
| GN-06 | Fixed in focused tests | Incorrect orphan-alert sweep removed. |
| GN-07 | Partly fixed | Tombstones hidden from ordinary API paths and archive DB/JSONL snapshots. Full two-phase deletion durability and every reader/export path remain to be independently audited. |
| GN-08 | Fixed for current schema | Current SQLite backup restores; historical-version compatibility and portable recovery still need a full drill. |
| GN-09 | Partly fixed | Worker revisits stale jobs, claims atomically, and does not resend an uncertain provider attempt. Multi-worker and crash fault injection remain. |
| GN-10 | Partly fixed | Client framing and identity handling strengthened. Server write/flush deadlines and real Windows pipe tests remain. |
| GN-11 | Partly fixed | Sender recreates client after credential rejection and broker retries bootstrap. Real outage/rotation tests remain. |
| GN-12 | Gated | App suspension and domain blocking default off on backend and broker; Windows undo/process/session safety remains open. |
| GN-13 | Open | Capture scope and docs now say primary monitor; secondary-monitor coverage and OCR legibility measurement remain. |
| GN-14 | Partly fixed | Onboarding requires a processed image event, and the dashboard no longer reports active protection on an empty installation. A dedicated end-to-end synthetic self-test and degraded-state UX remain. |
| GN-15 | Partly fixed | Child tray request/status path and strict parent review transitions added; standard-user and multi-session host tests remain. |
| GN-16 | Fixed in browser tests | Masked, accessible dialog replaces `window.prompt`; cancel, wrong password, success and mobile/desktop behavior tested with mocked API responses. |
| GN-17 | Fixed in backend tests | Valid token recovery uses the same per-device admission budget. |
| GN-18 | Open | Clean frozen integration, exact Windows artifact matrix, live provider evaluation and held-out capture quality still needed. |

## Evidence and limits

- Baseline before edits: `uv sync --frozen --extra dev` in backend and agent;
  317 backend and 75 agent tests passed. The handoff's earlier environment had
  different dependencies and its original twelve failures are preserved in the
  supplied ZIP, not claimed as our own clean baseline.
- Candidate source tests: 337 backend, 90 agent, 66 root, one synthetic API
  end-to-end test, 21 dashboard unit tests, and 10 mocked Playwright browser
  tests passed. Backend and agent Ruff checks and dashboard typecheck/build
  passed. Backend locked environment: Python 3.12.13, SQLAlchemy 2.0.51,
  cryptography 50.0.1, pytest 9.1.1, FastAPI 0.139.0.
- After CI identified new advisories, both Python locks were updated to Pillow
  13.0.0 and certifi 2026.10.23. Frozen backend/agent tests, backend mypy,
  and strict pip-audit then passed. Dashboard lock updates cleared high-severity
  npm audit findings; `npm audit --audit-level=high`, typecheck, 21 unit tests,
  10 Playwright tests, and production build passed. A moderate advisory in
  `minimatch`, through the development-only OpenAPI generator, remains; npm's
  proposed force fix would downgrade the generator across a major version.
- The supplied twelve regressions passed with `GN_REVIEW_SOURCE` set to this
  checkout and `uv run --frozen --extra dev --with psutil==7.2.2 --with
  mss==10.2.0 python -m pytest -q /tmp/gn-independent-repros.wMDPDB/repros`.
  The two additional packages are exact agent-lock versions needed to import
  the Windows broker into the backend test environment.
- Windows5 SSH was reachable for read-only inspection on 2026-10-31; the
  renderserve backend host was unreachable from this workspace. No installer
  upgrade or live family-data test was performed.
- The handoff's Python 3.13 diagnostic run reported an intermittent agent
  resource warning when the full suite ran together. The frozen Python 3.12
  agent suite passed here, but the warning's root cause has not been isolated
  across the original environment and remains a release investigation item.
- A separate real-backend browser smoke used a fresh temporary SQLite database
  and followed setup to the dashboard. It exposed a false green status with
  zero devices and zero captures. After correction, sign-in displayed
  "Coverage needs checking" and "No captures received yet" with no browser
  errors. The Vite development proxy now preserves Host for the backend Origin
  check. This smoke did not exercise real capture, OCR, or provider calls.
- The synthetic browser data directory is private mode `0700` under `/tmp`.
  A cleanup command was rejected by automatic command review, so it was left
  untouched; no family data or live credential was used.
- GitHub CI run `41210168405` on code commit `fb3959f` passed all seven jobs:
  backend, agent, Windows bundle, dashboard, Docker canary, release scripts,
  and actionlint. This verifies source and build gates, not a Windows install.

This file records implemented code and evidence without converting a passing
unit suite into a claim of field readiness. Update it after frozen full-suite,
Windows artifact and recovery qualification.

## Recheck commands

Run from the named directory in a clean checkout:

```text
backend/:       uv sync --frozen --extra dev
backend/:       uv run --frozen --extra dev pytest -q --tb=short
backend/:       uv run --frozen --extra dev pytest -q ../tests/e2e --tb=short
backend/:       uv run --frozen --extra dev ruff check app tests
agent-windows/: uv sync --frozen --extra dev
agent-windows/: uv run --frozen --extra dev pytest -q --tb=short
agent-windows/: uv run --frozen --extra dev ruff check src tests
dashboard/:     npm run typecheck
dashboard/:     npm test -- --run
dashboard/:     npm run test:e2e
dashboard/:     npm run build
repo root:      python3 -m pytest -q tests --ignore=tests/e2e --tb=short
```

The Browser plugin was unavailable in this session, so rendered validation
used the repository's Playwright configuration at `127.0.0.1:5199` with 1440×1000
and 390×844 viewports. The isolated real-backend smoke used a loopback Vite
proxy to a disposable backend at `127.0.0.1:8787`.
