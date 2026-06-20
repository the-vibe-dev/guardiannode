# GuardianNode Backend

FastAPI app providing local event ingestion, best-effort text filtering,
encryption, rules + Ollama LLM classification, and the parent dashboard API.

See [`../docs/BACKEND_SETUP.md`](../docs/BACKEND_SETUP.md) for setup instructions.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8787/setup`.

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

The current alpha initializes SQLite with SQLAlchemy `Base.metadata.create_all()`
and idempotent startup schema patches. Formal Alembic migrations are planned
before stable release; do not run `alembic upgrade head` in this checkout.

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
