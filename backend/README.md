# GuardianNode Backend

FastAPI app providing local event ingestion, best-effort text filtering,
encryption, rules + Ollama LLM classification, and the parent dashboard API.

See [`../docs/BACKEND_SETUP.md`](../docs/BACKEND_SETUP.md) for setup instructions.

## Run

```bash
cd backend
uv sync --frozen --extra dev
uv run guardiannode-backend
```

Then follow the setup instructions at `https://127.0.0.1:8787/setup`, including
trusting the generated family CA and obtaining the local one-time setup token.
The linked setup guide also documents an explicit loopback-only HTTP development
command.

## Layout

- `app/main.py` — FastAPI app + lifespan
- `app/settings.py` — config via env
- `app/api/` — HTTP endpoints
- `app/services/` — business logic (encryption, redaction, classifier, etc.)
- `app/db/` — SQLAlchemy models + session
- `app/workers/` — background workers
- `app/prompts/` — LLM prompt templates
- `tests/` — pytest suite

## Database Schema

The backend applies the bundled Alembic migration chain during normal startup.
This reviewed source includes revision `0008_notification_delivery`. Migration
tests cover existing schema/data upgrades; preserve a verified complete backup
before an upgrade. In-place downgrade is unsupported: restore a compatible
backup together with its matching application/configuration. See
[`../START_HERE.md`](../START_HERE.md) for this review build's upgrade guidance.

## Database Maintenance

File-backed SQLite installs include a small maintenance command:

```bash
guardiannode-db integrity
guardiannode-db backup ~/guardiannode-backup.sqlite
guardiannode-db restore ~/guardiannode-backup.sqlite
```

`backup` uses SQLite's online backup API and verifies the generated file before
publishing it. `restore` verifies the backup first and moves the previous live
database into `backups/` instead of deleting it. Stop the backend before running
`restore`.
