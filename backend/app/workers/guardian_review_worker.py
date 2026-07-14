"""Durable Guardian Review queue worker."""
from __future__ import annotations

import asyncio
import logging

from app import settings as settings_mod
from app.db.session import get_sessionmaker
from app.services import guardian_review

log = logging.getLogger(__name__)


async def run_once() -> bool:
    db = get_sessionmaker()()
    try:
        return await guardian_review.process_one(db)
    finally:
        db.close()


async def loop() -> None:
    db = get_sessionmaker()()
    try:
        recovered = guardian_review.recover_stale_jobs(db)
        if recovered:
            log.warning("requeued %d stale Guardian Review job(s)", recovered)
    finally:
        db.close()
    while True:
        try:
            processed = await run_once()
        except Exception as exc:  # pragma: no cover - supervisor handles repeated failures
            log.warning("Guardian Review worker failed safely: %s", type(exc).__name__)
            processed = False
        if not processed:
            await asyncio.sleep(settings_mod.settings.guardian_review_worker_interval_seconds)
