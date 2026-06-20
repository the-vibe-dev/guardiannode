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
| `GUARDIANNODE_BIND_HOST` | `127.0.0.1` | Set to `0.0.0.0` for LAN |
| `GUARDIANNODE_BIND_PORT` | `8787` | |
| `GUARDIANNODE_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama |
| `GUARDIANNODE_DB_URL` | `sqlite:///{data_dir}/guardiannode.db` | Postgres optional |
| `GUARDIANNODE_LOG_LEVEL` | `INFO` | |
| `GUARDIANNODE_DEV_MODE` | `0` | Disables auth-required for /dev endpoints |

## First run

1. Backend creates `~/.guardiannode/keys/master.key` (random 32 bytes, AES-GCM).
2. Backend creates `~/.guardiannode/guardiannode.db` (SQLite).
3. mDNS advertiser starts on local network.
4. Setup wizard at `/setup` prompts for admin account.

## Production install (Windows)

Via the Server Installer — registers `GuardianNodeBackend` as a Windows service via WinSW.

## Production install (Linux)

Via `install.sh` — registers `guardiannode-backend.service` systemd unit running as the `guardiannode` user.

## Database Schema

The current alpha uses SQLAlchemy `Base.metadata.create_all()` plus idempotent
startup schema patches for SQLite. Formal Alembic migrations are planned before
stable release, but this checkout does not include an Alembic migration tree.

## API docs

OpenAPI/Swagger at `http://127.0.0.1:8787/docs` (dev mode only).
