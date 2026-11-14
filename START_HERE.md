# GuardianNode - screenshot capture and AI review

Review source: **2026-11-13-review.4** · Application: **0.1.0-alpha.3** · Status: **alpha / developer preview**

This edition integrates the supplied review.4 package, preserves its
dependency and release-workflow updates, and follows the product direction:
screenshot capture, AI-assisted assessment and parent evidence review. It
improves capture correctness, processing authority and evidence review while
preserving capture consent, privacy controls and local storage safeguards.

## Read first

1. [Current integration record](docs/release-validation/screenshot-review4-2026-11-13.md):
   fixes in this edition, remaining gaps and verification.
2. [Screenshot and AI review workflow](docs/SCREENSHOT_REVIEW.md): capture,
   processing, evidence, feedback and per-device status.
3. [Legacy restriction recovery](docs/ENFORCEMENT.md): upgrade compatibility and
   release-only recovery for actions created by older versions.
4. [Capture queue operations](docs/CAPTURE_QUEUE_OPERATIONS.md) and
   [notification routing](docs/NOTIFICATIONS.md): storage, retries and delivery.
5. [Backend setup](docs/BACKEND_SETUP.md) and [Windows agent](agent-windows/README.md):
   development and deployment prerequisites.

The matched production dashboard is included in `backend/app/static`. This
repository contains source, frozen dependency manifests, tests and installer
sources. No newly built or signed Windows installer is included.

The original licensing and historical Build Week/release records remain intact.
Historical counts and qualifications apply to their original builds only. The
current validation record is the authority for this edition's checks. The earlier
[review.3 integration record](docs/release-validation/screenshot-review-2026-11-13.md)
remains as provenance for changes already present in the supplied ZIP.

## Evaluate from source

Use a disposable environment and synthetic data first. Python 3.11+ is required by the projects. Native Windows evaluation also needs the documented Windows extras and platform tools. The dashboard's production assets are included in `backend/app/static`.

From the source root:

```sh
cd backend
uv sync --frozen --extra dev
uv run guardiannode-backend
```

Follow the existing [backend setup guide](docs/BACKEND_SETUP.md) for the local setup token, family CA, HTTPS, data location, Tesseract, Ollama, and model configuration. The new consent gates keep public device collection disabled until a parent account and active applicable consent exist. Disabling screenshot collection or retention pauses new screenshot monitoring; no ephemeral processing mode is implemented.

The default encrypted deployment should remain on the trusted family network. A source development HTTP override is only for explicit loopback evaluation; do not use it for a LAN or public deployment. The reviewed Linux host-network Compose override keeps Ollama on loopback, but this build has not been run through Docker here.

To rebuild the dashboard after making changes:

```sh
cd dashboard
npm ci
npm run typecheck
npm test
npm run build
```

Replace the complete contents of `backend/app/static` with `dashboard/dist` after a successful build. Do not combine a new index file with stale hashed assets. Build and copy the production assets from this branch before release.

The [Windows agent guide](agent-windows/README.md) and [native build guide](docs/POWER_USER_INSTALL.md) describe the native paths. Build and qualify the exact Windows artifacts before using this screenshot-review build beyond technical evaluation. Do not reuse an old installer while assuming it contains these source changes.

## Upgrade an existing instance

1. Record the existing deployment paths, service definitions, environment/configuration, TLS enrollment, version, and recovery material. Stop or quiesce writers before a deployment-level backup.
2. Back up the complete data/configuration/key/evidence set required for recovery. Keep the previous application and dependency environment. The portable archive commands below cover the supported application archive; preserve external service definitions and operator configuration separately.
3. Create and verify a portable archive, and export its signer identity. Run with the existing instance's data-directory configuration. Use secure absolute paths appropriate to the host:

```sh
cd backend
uv run guardiannode-archive create /secure-backups/pre-review.gna --mode portable --passphrase
uv run guardiannode-archive verify /secure-backups/pre-review.gna --passphrase
uv run guardiannode-archive signer-export /secure-backups/guardian-signer.pub
```

The commands prompt for a passphrase; do not place it in the shell command or commit it. Verify a restore into an empty disposable target before relying on the archive:

```sh
uv run guardiannode-archive restore /secure-backups/pre-review.gna --target /safe-empty-restore --trusted-signer /secure-backups/guardian-signer.pub --passphrase --dry-run
```

Then perform an actual restore into a separate empty target and verify synthetic evidence decryption and application behavior. A dry run alone is not a full disaster-recovery rehearsal. Preserve the trusted signer and recovery credentials independently of the machine being recovered.

4. Install this source with its frozen dependencies and matching compiled dashboard. Normal backend startup upgrades to Alembic revision `0008_notification_delivery`; this adds durable per-channel delivery state and digest retry fields. Verify readiness and logs before returning the instance to service.
5. Undo active app/domain restrictions with the old endpoint before upgrading it. The new endpoint is release-only: it retires verified old app-pause leases and removes owned legacy hosts entries. Numeric-PID-only records stay unverified; preserve corrupt or unresolved state for operator recovery. Install matching backend, dashboard and endpoint versions. Verify pairing, capture, OCR/AI review, screenshot-monitoring pause/resume, policy-cache restart, notifications, consent opt-outs, withdrawal/deletion and offline recovery with synthetic data. See [legacy recovery](docs/ENFORCEMENT.md).
6. If rollback is required, restore a compatible complete backup with the matching old application. This migration has no supported in-place downgrade. Moving old code back without restoring its compatible database/configuration is insufficient.

Existing historical digests are not reconstructed by this change. Subsequent digests cover the previous complete local calendar day. Withdrawal cannot recall a message or provider request already transmitted, reach an offline endpoint instantly, or erase existing exported backups/downloads.

## Reproduce the checks

```sh
cd backend
uv run pytest -q tests ../tests/e2e
uv run ruff check app tests migrations/versions/0008_notification_delivery.py
uv run mypy app
```

```sh
cd agent-windows
uv sync --frozen --extra dev
uv run pytest -q tests
uv run ruff check src tests
```

```sh
# From the source root, using the backend environment:
backend/.venv/bin/python -m pytest -q tests --ignore=tests/e2e
backend/.venv/bin/python scripts/run_classifier_benchmark.py --mode rules
backend/.venv/bin/python scripts/check_build_week_submission.py
```

Windows shells use the corresponding `.venv\Scripts\python.exe` path. The root repository controls explicitly report that a source ZIP cannot verify Git history or the historical baseline tag.

## What should improve next

Priorities are native Windows capture qualification, explicit multi-display
coverage, representative OCR/AI evaluation, durable capture/drop diagnostics,
optional capture exclusions, better incident/evidence navigation, and signed
installers with qualified updates and rollback. Read [the focused roadmap](docs/ROADMAP.md)
and [the current integration record](docs/release-validation/screenshot-review4-2026-11-13.md).

Screen-time budgets, usage schedules, website/app blocking and exception requests
are outside the chosen product scope. Retention, queue bounds and request-size
controls remain operational safeguards; they do not restrict a child's browsing
or device use.

No source-test result establishes real-world detection accuracy or qualifies a
native Windows installer. The current validation record separates executed checks from
remaining release gates.
