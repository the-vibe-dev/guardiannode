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
