from __future__ import annotations

from pathlib import Path

import pytest
from ulid import ULID

from app import settings as settings_mod
from app.services import screenshot_async


def test_parent_capture_wipe_removes_pending_and_dead_letters_only(tmp_path):
    first = screenshot_async.store_pending(b"pending", {"device_id": "synthetic"})
    second = screenshot_async.store_pending(b"dead", {"device_id": "synthetic"})
    screenshot_async._quarantine(second, "synthetic failure")
    root = settings_mod.settings.data_dir
    keep = root / "pending" / "README.txt"
    keep.write_text("preserve unrelated files")
    temp = root / "pending" / f".{ULID()}.enc.{ULID()}.tmp"
    temp.write_bytes(b"incomplete")

    result = screenshot_async.purge_pending_capture_files()

    assert result == {"deleted": 5, "failed": 0}
    assert not (root / "pending" / f"{first}.enc").exists()
    assert not (root / "pending_dead_letter" / f"{second}.enc").exists()
    assert keep.read_text() == "preserve unrelated files"


def test_capture_wipe_reports_locked_files(tmp_path, monkeypatch):
    token = screenshot_async.store_pending(b"pending", {"device_id": "synthetic"})
    locked = settings_mod.settings.data_dir / "pending" / f"{token}.enc"
    real_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == locked:
            raise PermissionError("synthetic file lock")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    assert screenshot_async.purge_pending_capture_files() == {"deleted": 1, "failed": 1}
    assert locked.exists()


def test_capture_wipe_refuses_symlink_files_and_directories(tmp_path):
    root = settings_mod.settings.data_dir
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / f"{ULID()}.enc"
    victim.write_bytes(b"preserve outside data")
    pending = root / "pending"
    pending.mkdir()
    (pending / f"{ULID()}.enc").symlink_to(victim)
    (root / "pending_dead_letter").symlink_to(outside, target_is_directory=True)
    assert screenshot_async.purge_pending_capture_files() == {"deleted": 0, "failed": 2}
    assert victim.read_bytes() == b"preserve outside data"


def test_capture_wipe_has_bounded_file_budget():
    screenshot_async.store_pending(b"pending", {"device_id": "synthetic"})
    assert screenshot_async.purge_pending_capture_files(limit=1) == {"deleted": 1, "failed": 1}


@pytest.mark.asyncio
async def test_stale_queue_token_after_parent_wipe_does_not_recreate_files():
    token = screenshot_async.store_pending(b"pending", {"device_id": "synthetic"})
    assert screenshot_async.purge_pending_capture_files()["failed"] == 0
    await screenshot_async._classify_token(token)
    assert not (settings_mod.settings.data_dir / "pending_dead_letter" / f"{token}.json").exists()
