"""Decouple screenshot upload from classification.

Why: classifying a frame on the vision LLM takes tens of seconds. If the agent
had to wait for that on every upload, frames would pile up in the agent's local
queue and be LOST the moment the child powers the PC off. Instead the backend
stores each uploaded frame to disk (encrypted) the instant it arrives — so it
survives a power-off — and a single background worker classifies the pending
frames one at a time. Single worker = the vision model is never hit
concurrently (no "2 frames processing" thrash).

On disk:
  <data>/pending/<token>.enc   — AES-GCM encrypted JPEG bytes
  <data>/pending/<token>.json  — capture metadata (cleartext: app, device, etc.)

Pending files outlive a backend restart; they are re-enqueued on startup, so a
crash or power-off of the *server* doesn't drop unclassified frames either.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ulid import ULID

from app.services import encryption, screenshot_ingest
from app.settings import settings

log = logging.getLogger(__name__)

_queue: asyncio.Queue | None = None
_MAX_PENDING = 500  # backpressure: refuse new frames if the server is this far behind


def _pending_dir() -> Path:
    p = settings.data_dir / "pending"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=_MAX_PENDING)
    return _queue


def pending_count() -> int:
    try:
        return len(list(_pending_dir().glob("*.json")))
    except Exception:
        return 0


def max_pending() -> int:
    return _MAX_PENDING


def store_pending(image_bytes: bytes, meta: dict[str, Any]) -> str:
    """Persist a frame (encrypted) + its metadata, return its token. Fast."""
    token = str(ULID())
    d = _pending_dir()
    encryption.encrypt_blob_to_disk(image_bytes, d / f"{token}.enc", aad=token.encode("ascii"))
    meta = {**meta, "token": token, "stored_at": datetime.now(timezone.utc).isoformat()}
    (d / f"{token}.json").write_text(json.dumps(meta), encoding="utf-8")
    return token


def enqueue_nowait(token: str) -> bool:
    try:
        get_queue().put_nowait(token)
        return True
    except asyncio.QueueFull:
        return False


def _load_meta(token: str) -> dict[str, Any] | None:
    try:
        return json.loads((_pending_dir() / f"{token}.json").read_text("utf-8"))
    except Exception:
        return None


def _discard(token: str) -> None:
    for suffix in (".enc", ".json"):
        try:
            (_pending_dir() / f"{token}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


def discard(token: str) -> None:
    _discard(token)


async def _classify_token(token: str) -> None:
    from app.db.session import get_sessionmaker

    meta = _load_meta(token)
    if meta is None:
        _discard(token)
        return
    try:
        image_bytes = encryption.decrypt_blob_from_disk(
            _pending_dir() / f"{token}.enc", aad=token.encode("ascii")
        )
    except Exception as e:
        log.warning("pending frame %s unreadable (%s); discarding", token, e)
        _discard(token)
        return

    ts = meta.get("timestamp")
    try:
        timestamp = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    except Exception:
        timestamp = datetime.now(timezone.utc)

    session = get_sessionmaker()()
    try:
        await screenshot_ingest.ingest_screenshot(
            session,
            image_bytes=image_bytes,
            device_id=meta["device_id"],
            app_name=meta.get("app_name"),
            window_title=meta.get("window_title"),
            url=meta.get("url"),
            profile_id=meta.get("profile_id"),
            age_group=meta.get("age_group", "10_13"),
            capture_scope=meta.get("capture_scope", "monitored_app"),
            policy_id=meta.get("policy_id"),
            policy_version=meta.get("policy_version"),
            collector_version=meta.get("collector_version"),
            timestamp=timestamp,
            source_ip=meta.get("source_ip"),
        )
        session.commit()
    finally:
        session.close()
        # The classifier stored its own evidence blob if the frame was risky;
        # the pending copy is no longer needed either way.
        _discard(token)


async def loop() -> None:
    """Single-consumer worker: classify pending frames one at a time."""
    q = get_queue()
    # Re-enqueue frames left on disk by a previous run (crash / restart / power-off).
    for jf in sorted(_pending_dir().glob("*.json")):
        try:
            q.put_nowait(jf.stem)
        except asyncio.QueueFull:
            break
    if q.qsize():
        log.info("re-enqueued %d pending frame(s) from disk", q.qsize())
    while True:
        try:
            token = await asyncio.wait_for(q.get(), timeout=30.0)
        except asyncio.TimeoutError:
            for jf in sorted(_pending_dir().glob("*.json")):
                if q.full():
                    break
                q.put_nowait(jf.stem)
            continue
        try:
            await _classify_token(token)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("classification of %s failed: %s", token, e)
            _discard(token)
        finally:
            q.task_done()
