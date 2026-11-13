# GuardianNode — November review integration

Review source: **2026-11-13-review.2** · Application: **0.1.0-alpha.3** · Status: **alpha / developer preview**

This branch integrates the reviewed source and rebuilds the parent dashboard. The supplied review PDF and ZIP are stored locally in `.ignored-cleanup/review-2026-11-13/`, outside Git. This source integration does not qualify a signed Windows installer, native Windows behavior, Docker deployment, or browsers.

## Read first

1. [Capture queue operations](docs/CAPTURE_QUEUE_OPERATIONS.md): pending capture state, cleanup, and recovery.
2. [Audit and action history](docs/AUDIT_AND_ACTION_HISTORY.md): pagination, action records, and Undo.
3. [Notification routing](docs/NOTIFICATIONS.md): current-policy delivery and retry behavior.
4. [Backend setup](docs/BACKEND_SETUP.md) and [Windows agent](agent-windows/README.md): development and deployment prerequisites.

The reviewed changes add audit pagination, independent Settings drafts, current-policy notification delivery, bounded quarantine cleanup, durable withdrawal retries, safer app pause leases, and parent action history/Undo. The review archive reported 799 passing automated tests in its isolated source tree; this integration requires its own verification.

Read [Capture queue operations](docs/CAPTURE_QUEUE_OPERATIONS.md), [Audit and action history](docs/AUDIT_AND_ACTION_HISTORY.md), and [Notification routing](docs/NOTIFICATIONS.md) for the new operating contracts.

The original AGPL-3.0 licensing and historical Build Week records remain in the project. Those historical records do not qualify this changed build. The deterministic rules version is `0.1.0-alpha.3-review.1`.

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

The [Windows agent guide](agent-windows/README.md) and [native build guide](docs/POWER_USER_INSTALL.md) describe the native paths. Build and qualify the exact Windows artifacts before using this review build beyond technical evaluation. Do not reuse an old installer while assuming it contains these source changes.

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
5. Undo active app pauses with the old endpoint before upgrading it. Legacy numeric-PID records become unverified rather than resuming a possibly unrelated process. Preserve corrupt/unresolved state for verified recovery. Install the matching reviewed endpoint build on a Windows test machine. Verify pair, capture, alert, pause/resume, policy-cache restart, notification configuration, consent opt-outs, withdrawal/delete, and offline recovery with synthetic data.
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

## What is still missing

Major remaining items include signed installers and upgrades, complete rollback qualification, a measured usage/screen-time engine, persistent category/content filtering, more child-device platforms, named second-parent accounts, complete coverage/drop telemetry, native provider adapters, and representative detection evaluation. Child request approval currently records the parent decision; it does not create an automatic screen-time extension or unblock rule.

The tests provide regression evidence, but do not prove real-world detection accuracy or substitute for the native release matrix. Review the locally retained PDF before promoting this alpha build.
