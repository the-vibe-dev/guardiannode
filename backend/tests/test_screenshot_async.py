from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from app.services import screenshot_async


def _pending_file(tmp_path, token: str, *, stored_at: datetime, mtime: float) -> None:
    pending = tmp_path / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    meta = {"token": token, "stored_at": stored_at.isoformat(), "device_id": "dev-1"}
    (pending / f"{token}.json").write_text(json.dumps(meta), encoding="utf-8")
    (pending / f"{token}.enc").write_bytes(b"ciphertext")
    os.utime(pending / f"{token}.json", (mtime, mtime))
    os.utime(pending / f"{token}.enc", (mtime, mtime))


def test_requeue_pending_newest_first_and_discards_stale_backlog(monkeypatch, tmp_path):
    monkeypatch.setattr(screenshot_async.settings_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(screenshot_async.settings_mod.settings, "pending_frame_max_age_seconds", 600)
    monkeypatch.setattr(screenshot_async.settings_mod.settings, "pending_replay_max_frames", 2)

    now = datetime.now(UTC)
    _pending_file(tmp_path, "old-fresh", stored_at=now, mtime=10)
    _pending_file(tmp_path, "newer", stored_at=now, mtime=20)
    _pending_file(tmp_path, "newest", stored_at=now, mtime=30)
    _pending_file(tmp_path, "stale", stored_at=now - timedelta(hours=1), mtime=40)

    q: asyncio.Queue = asyncio.Queue(maxsize=10)

    assert screenshot_async.requeue_pending(q) == 2
    assert q.get_nowait() == "newest"
    assert q.get_nowait() == "newer"
    assert not (tmp_path / "pending" / "stale.json").exists()
    assert not (tmp_path / "pending" / "old-fresh.json").exists()


@pytest.mark.asyncio
async def test_default_queue_is_round_robin_while_preserving_device_fifo():
    tokens = []
    for device_id in ("child-a", "child-a", "child-b", "child-a", "child-b"):
        token = screenshot_async.store_pending(b"frame", {"device_id": device_id})
        tokens.append(token)

    queue = screenshot_async.FairDeviceQueue(maxsize=10)
    for token in tokens:
        queue.put_nowait(token)

    observed = [await queue.get() for _ in tokens]
    assert observed == [tokens[0], tokens[2], tokens[1], tokens[4], tokens[3]]


def test_per_device_pending_cap_preserves_capacity_for_siblings(monkeypatch):
    monkeypatch.setattr(screenshot_async, "_MAX_DEVICE_PENDING", 2)
    screenshot_async.store_pending(b"one", {"device_id": "child-a"})
    screenshot_async.store_pending(b"two", {"device_id": "child-a"})

    accepted_a, _ = screenshot_async.can_accept("child-a", 3)
    accepted_b, _ = screenshot_async.can_accept("child-b", 3)
    assert accepted_a is False
    assert accepted_b is True
