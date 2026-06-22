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
| `GUARDIANNODE_DB_URL` | `sqlite:///{data_dir}/guardiannode.db` | Postgres optional |
| `GUARDIANNODE_LOG_LEVEL` | `INFO` | |
| `GUARDIANNODE_DEV_MODE` | `0` | Disables auth-required for /dev endpoints |

After logging in as the parent, `GET /api/health/runtime-settings` returns the
effective non-secret runtime configuration: bind host/port, classifier tier,
model names, role-specific Ollama URLs, classifier timeouts/context settings,
and security/runtime flags. Use this to verify an installer-written
`server.env` was loaded as expected.

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

The current alpha uses SQLAlchemy `Base.metadata.create_all()` plus idempotent
startup schema patches for SQLite. Formal Alembic migrations are planned before
stable release, but this checkout does not include an Alembic migration tree.

## API docs

OpenAPI/Swagger at `http://127.0.0.1:8787/docs` (dev mode only).
