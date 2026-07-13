# Backend Setup

## Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8787
```

Dashboard at `http://127.0.0.1:8787/setup` for first-run wizard.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `GUARDIANNODE_DATA_DIR` | `~/.guardiannode` | Where DB + evidence + keys live |
| `GUARDIANNODE_BIND_HOST` | `127.0.0.1` | Keep loopback for first-run setup; expose LAN only after setup is complete |
| `GUARDIANNODE_BIND_PORT` | `8787` | |
| `GUARDIANNODE_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama |
| `GUARDIANNODE_CLASSIFIER_MODE` | unset | Explicit mode: `rules_only`, `text_llm`, `vision`, or `full` |
| `GUARDIANNODE_CLASSIFIER_TIER` | `text_only` | Legacy compatibility setting; `text_only` maps to `text_llm` and `vision_only` maps to `vision` |
| `GUARDIANNODE_OCR_LANGUAGES` | `eng` | Comma-separated Tesseract language data required for readiness |
| `GUARDIANNODE_DB_URL` | `sqlite:///{data_dir}/guardiannode.db` | Postgres optional |
| `GUARDIANNODE_LOG_LEVEL` | `INFO` | |
| `GUARDIANNODE_DEV_MODE` | `0` | Disables auth-required for /dev endpoints |
| `GUARDIANNODE_DATABASE_BACKUP_ENABLED` | `true` | Run integrity-checked scheduled SQLite backups |
| `GUARDIANNODE_DATABASE_BACKUP_INTERVAL_SECONDS` | `86400` | Backup interval; minimum worker interval is 300 seconds |
| `GUARDIANNODE_DATABASE_BACKUP_KEEP` | `7` | Scheduled generations retained |
| `GUARDIANNODE_READINESS_MIN_FREE_BYTES` | `268435456` | Minimum free disk space required by `/api/health/ready` |

After logging in as the parent, `GET /api/health/runtime-settings` returns the
effective non-secret runtime configuration: bind host/port, classifier tier,
model names, role-specific Ollama URLs, classifier timeouts/context settings,
and security/runtime flags. Use this to verify an installer-written
`server.env` was loaded as expected. When both classifier variables are set,
the explicit mode wins.

Before starting a managed service, validate the active pipeline:

```bash
guardiannode-backend preflight --json
# Installers/Compose may explicitly initialize missing configured models:
guardiannode-backend preflight --pull-models --json
```

Exit code `0` is ready, `2` is invalid configuration, `3` is an unavailable
runtime dependency, and `4` is a missing or failed model initialization.

## First run

1. Backend creates the evidence master key (random 32 bytes, AES-GCM).
   GuardianNode encrypts retained screenshot blobs and collected event text with
   AES-256-GCM. On new Windows installations, the key is wrapped with Windows
   DPAPI in LocalMachine scope and stored as `keys/master.key.dpapi`. On Linux,
   macOS, and source deployments outside Windows, the current alpha stores
   `keys/master.key` with restrictive filesystem permissions. Upgraded Windows
   installations may retain a legacy raw key after generating a DPAPI-wrapped
   copy; verify a portable backup before removing the legacy file.
2. Backend creates `~/.guardiannode/guardiannode.db` (SQLite).
3. Backend creates a one-time setup token in `keys/setup_token.json`.
4. Setup wizard at `/setup` prompts for the setup token and admin account.

Create a portable, passphrase-encrypted key backup before moving the backend to
another machine. From a source checkout, run this in the `backend/` directory or
an installed backend Python environment:

```bash
python -m app.services.encryption export-key-backup ~/guardiannode-master-key-backup.json
```

Restore it when moving or recovering the backend:

```bash
python -m app.services.encryption import-key-backup ~/guardiannode-master-key-backup.json
```

Store that backup separately from the database and evidence directory. DPAPI
LocalMachine protects against casual file copying but is not a boundary against
a sufficiently privileged process on that machine. The 12-word recovery code
resets the parent dashboard account only. It cannot decrypt evidence and does
not replace a master-key backup.

## Production install (Windows)

Via the Server Installer — registers `GuardianNodeBackend` as a Windows service via WinSW.

## Production install (Linux)

Via `install.sh` — registers `guardiannode-backend.service` systemd unit running as the `guardiannode` user.

## Database Schema

Startup applies the Alembic migration tree before any worker starts. An existing
SQLite database is backed up under `backups/pre-migration-*.sqlite3` before its
revision changes, and startup fails if migration or post-migration integrity
validation fails. `/api/health/ready` verifies database access, schema revision,
encryption availability, disk headroom, required worker supervision, OCR/language
data, and the model endpoints required by the active classifier mode.

Historical Alembic revisions contain explicit immutable schema operations and
do not import current ORM metadata. The beta baseline supports forward upgrades
from the public alpha schema; destructive downgrade of that baseline is
intentionally unsupported.

Scheduled SQLite backups are stored under `backups/scheduled-*.sqlite3`. They
are created with SQLite's online backup API, integrity checked, fsynced, and
paired with a `.manifest.json` containing the schema revision and checksum.
Restore validates the manifest when present. Backups are pruned to the
configured retention count. For a manual backup or restore drill,
stop the backend service first for restore, then run from the backend environment:

```bash
python -m app.db.maintenance backup /safe/path/guardiannode.sqlite3
python -m app.db.maintenance integrity --database /safe/path/guardiannode.sqlite3
python -m app.db.maintenance restore /safe/path/guardiannode.sqlite3
```

Restore validates the backup and restored copy and retains the replaced live
database as `backups/pre-restore-*`. Database backups must be paired with the
portable evidence-key backup described above when recovering on another machine.

## API docs

OpenAPI/Swagger at `http://127.0.0.1:8787/docs` (dev mode only).
