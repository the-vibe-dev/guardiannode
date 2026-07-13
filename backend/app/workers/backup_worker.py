"""Scheduled integrity-checked SQLite backups with bounded retention."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from app import settings as settings_mod
from app.db.maintenance import backup_database, backup_manifest_path, sqlite_path_from_url

log = logging.getLogger(__name__)


def _scheduled_backups() -> list[Path]:
    return sorted(
        settings_mod.settings.backups_dir.glob("scheduled-*.sqlite3"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def run_once() -> Path | None:
    settings = settings_mod.settings
    try:
        source = sqlite_path_from_url(settings.db_url_resolved)
    except Exception:
        log.info("scheduled database backup skipped for non-SQLite database")
        return None
    destination = settings.backups_dir / (
        f"scheduled-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
    )
    backup_database(destination, source=source)
    keep = max(1, int(settings.database_backup_keep))
    for stale in _scheduled_backups()[keep:]:
        stale.unlink(missing_ok=True)
        backup_manifest_path(stale).unlink(missing_ok=True)
    log.info("scheduled database backup completed: %s", destination)
    return destination


async def loop() -> None:
    interval = max(300, int(settings_mod.settings.database_backup_interval_seconds))
    while True:
        try:
            await asyncio.to_thread(run_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("scheduled database backup failed: %s", exc)
        await asyncio.sleep(interval)
