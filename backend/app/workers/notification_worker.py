"""Background delivery for queued parent notifications."""
from __future__ import annotations

import asyncio
import logging

from app.db.session import get_sessionmaker
from app.services import notifications
from app.settings import settings

log = logging.getLogger(__name__)


def run_once(*, limit: int = 10) -> int:
    db = get_sessionmaker()()
    try:
        return notifications.process_pending(db, limit=limit)
    finally:
        db.close()


async def loop() -> None:
    while True:
        try:
            processed = run_once()
            if processed:
                log.info("processed %d notification job(s)", processed)
        except Exception as e:  # pragma: no cover
            log.warning("notification worker failed: %s", e)
        await asyncio.sleep(settings.notification_worker_interval_seconds)
