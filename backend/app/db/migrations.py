"""Alembic migration entry point with automatic pre-migration SQLite backup."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app import settings as settings_mod
from app.db.maintenance import backup_database, integrity_check, sqlite_path_from_url

log = logging.getLogger(__name__)
_migration_lock = Lock()


def _backend_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    root = _backend_root()
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings_mod.settings.db_url_resolved.replace("%", "%%"))
    return cfg


def schema_revisions(engine: Engine) -> tuple[str | None, str]:
    cfg = alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        raise RuntimeError("Alembic migration head is missing")
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current, head


def _backup_before_migration(engine: Engine, current: str | None, head: str) -> Path | None:
    if current == head or engine.dialect.name != "sqlite":
        return None
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    if not tables:
        return None
    source = sqlite_path_from_url(settings_mod.settings.db_url_resolved)
    destination = settings_mod.settings.backups_dir / (
        f"pre-migration-{current or 'alpha'}-to-{head}-"
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
    )
    backup_database(destination, source=source)
    log.info("created pre-migration database backup: %s", destination)
    return destination


def upgrade_schema(engine: Engine) -> dict[str, str | None]:
    # Alembic's environment/op proxies are process-global. Serializing startup
    # also prevents duplicate SQLite backups and partial concurrent DDL if two
    # ASGI lifespans are entered at once.
    with _migration_lock:
        current, head = schema_revisions(engine)
        backup = _backup_before_migration(engine, current, head)
        cfg = alembic_config()
        with engine.begin() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
        migrated, _ = schema_revisions(engine)
        if migrated != head:
            raise RuntimeError(f"database migration incomplete: expected {head}, found {migrated}")
        if engine.dialect.name == "sqlite":
            result = integrity_check(sqlite_path_from_url(settings_mod.settings.db_url_resolved))
            if not result.ok:
                raise RuntimeError(
                    "database failed integrity check after migration: "
                    + "; ".join(result.messages)
                )
        return {
            "previous_revision": current,
            "current_revision": migrated,
            "backup": str(backup) if backup is not None else None,
        }
