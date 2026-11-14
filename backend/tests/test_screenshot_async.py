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


def test_requeue_budget_retains_fresh_backlog_and_quarantines_expired_frames(monkeypatch, tmp_path):
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
    assert (tmp_path / "pending" / "old-fresh.json").exists()
    assert (tmp_path / "pending" / "old-fresh.enc").exists()
    dead_meta = json.loads((tmp_path / "pending_dead_letter" / "stale.json").read_text())
    assert dead_meta["dead_letter_reason"] == "capture_expired_before_review"
    assert (tmp_path / "pending_dead_letter" / "stale.enc").exists()


@pytest.mark.asyncio
async def test_more_than_fifty_accepted_frames_survive_replay_rounds_and_restart(monkeypatch):
    monkeypatch.setattr(screenshot_async.settings_mod.settings, "pending_replay_max_frames", 50)
    tokens = []
    for index in range(70):
        device_id = f"child-{index % 2}"
        assert screenshot_async.can_accept(device_id, 15)[0] is True
        tokens.append(screenshot_async.store_pending(b"synthetic frame", {"device_id": device_id}))

    first_queue = screenshot_async.FairDeviceQueue(maxsize=500)
    assert screenshot_async.requeue_pending(first_queue) == 50
    assert screenshot_async.pending_count() == 70
    first_batch = [await first_queue.get() for _ in range(50)]
    for token in first_batch:
        screenshot_async.discard(token)
    assert screenshot_async.pending_count() == 20

    # A fresh queue models a service restart; every accepted remaining token is
    # still discoverable and is only removed after its processing completes.
    restarted_queue = screenshot_async.FairDeviceQueue(maxsize=500)
    assert screenshot_async.requeue_pending(restarted_queue) == 20
    second_batch = [await restarted_queue.get() for _ in range(20)]
    assert set(first_batch).isdisjoint(second_batch)
    assert set(first_batch + second_batch) == set(tokens)
    for token in second_batch:
        screenshot_async.discard(token)
    assert screenshot_async.pending_count() == 0


@pytest.mark.asyncio
async def test_expired_retry_is_quarantined_with_its_encrypted_frame(monkeypatch):
    from app.services import encryption

    monkeypatch.setattr(screenshot_async.settings_mod.settings, "pending_frame_max_age_seconds", 600)
    token = screenshot_async.store_pending(b"synthetic frame", {"device_id": "child-a"})
    metadata = screenshot_async._load_meta(token)
    metadata.update(stored_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(), attempts=4)
    screenshot_async._write_meta(token, metadata)

    await screenshot_async._classify_token(token)

    assert screenshot_async._load_meta(token) is None
    dead = screenshot_async._dead_letter_dir()
    metadata = json.loads((dead / f"{token}.json").read_text())
    assert metadata["dead_letter_reason"] == "capture_expired_before_review"
    assert metadata["attempts"] == 4
    assert encryption.decrypt_blob_from_disk(dead / f"{token}.enc", aad=token.encode("ascii")) == b"synthetic frame"


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


def test_queue_is_recreated_for_new_event_loop(monkeypatch):
    monkeypatch.setattr(screenshot_async, "_queue", None)

    async def bind_queue():
        queue = screenshot_async.get_queue()
        try:
            await asyncio.wait_for(queue.get(), timeout=0.01)
        except TimeoutError:
            pass
        return queue

    first = asyncio.run(bind_queue())
    second = asyncio.run(bind_queue())
    assert second is not first


@pytest.mark.asyncio
async def test_duplicate_replay_does_not_reclassify_same_frame():
    token = screenshot_async.store_pending(b"synthetic frame", {"device_id": "dev-1"})
    queue = screenshot_async.FairDeviceQueue(maxsize=10)
    queue.put_nowait(token)
    queue.put_nowait(token)
    assert queue.qsize() == 1
    assert await queue.get() == token
    assert queue.qsize() == 0
