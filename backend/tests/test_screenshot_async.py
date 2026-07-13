from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

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
