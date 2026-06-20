"""Periodic retention cleanup worker."""
from __future__ import annotations

import asyncio
import json
import logging

from app.db.models import Setting
from app.db.session import get_sessionmaker
from app.services import retention
from app.settings import settings

log = logging.getLogger(__name__)


def _retention_settings(session) -> dict[str, int]:
    row = session.get(Setting, "retention_settings")
    if not row or not row.value:
        return dict(retention.DEFAULT_RETENTION_DAYS)
    try:
        data = json.loads(row.value)
    except Exception:
        return dict(retention.DEFAULT_RETENTION_DAYS)
    if not isinstance(data, dict):
        return dict(retention.DEFAULT_RETENTION_DAYS)
    return {**retention.DEFAULT_RETENTION_DAYS, **data}


def run_once() -> dict[str, int]:
    db = get_sessionmaker()()
    try:
        result = retention.run_cleanup(db, _retention_settings(db))
        log.info("retention cleanup completed: %s", result)
        return result
    finally:
        db.close()


async def loop() -> None:
    interval = max(60, int(settings.retention_cleanup_interval_seconds))
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(run_once)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("retention cleanup failed: %s", e)
