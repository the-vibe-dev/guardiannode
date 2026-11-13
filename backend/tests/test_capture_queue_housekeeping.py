from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ulid import ULID

from app.db.models import Setting
from app.services import capture_queue, screenshot_async
from app.workers import cleanup_worker


def _file(root, directory="pending_dead_letter", *, token=None, suffix=".enc", age=0, size=16):
    folder = root / directory
    folder.mkdir(exist_ok=True)
    path = folder / f"{token or ULID()}{suffix}"
    path.write_bytes(b"x" * size)
    when = (datetime.now(UTC) - timedelta(days=age)).timestamp()
    os.utime(path, (when, when))
    return path


def _run(db, **kwargs):
    result = capture_queue.run_cleanup(db, **kwargs)
    db.commit()
    return result


def test_ttl_expires_quarantine_pairs_and_orphans_but_never_live_pending(db_session, tmp_path):
    token = str(ULID())
    expired = [
        _file(tmp_path, token=token, age=8),
        _file(tmp_path, token=token, suffix=".json", age=8),
        _file(tmp_path, age=8),
        _file(tmp_path, suffix=".json", age=8),
        _file(tmp_path, token=f".{ULID()}.enc.{ULID()}", suffix=".tmp", age=8),
    ]
    live = _file(tmp_path, "pending", age=300)
    young = _file(tmp_path, age=1)
    unrelated = tmp_path / "pending_dead_letter" / "notes.txt"
    unrelated.write_text("keep")

    result = _run(db_session)

    assert result["deleted_files"] == result["expired_files"] == 5
    assert result["quota_files"] == result["failed_files"] == 0
    assert not any(path.exists() for path in expired)
    assert live.exists() and young.exists() and unrelated.exists()


def test_pair_age_uses_newer_file_without_parsing_malformed_metadata(db_session, tmp_path, monkeypatch):
    token = str(ULID())
    enc = _file(tmp_path, token=token, age=30)
    meta = _file(tmp_path, token=token, suffix=".json", age=1)
    meta.write_text("{private malformed data, URL, title, error}")
    monkeypatch.setattr(Path, "read_text", lambda *_a, **_k: pytest.fail("Must not read capture contents"))

    result = _run(db_session)
    public = capture_queue.status(db_session)

    assert result["deleted_files"] == 0 and enc.exists() and meta.exists()
    assert public["dead_letter"]["frames"] == 1
    assert public["dead_letter"]["orphan_files"] == 0


def test_quota_removes_oldest_frame_and_preserves_younger_frames(db_session, tmp_path):
    capture_queue.set_policy(db_session, {"dead_letter_max_bytes": 1024 * 1024})
    old_token, new_token = str(ULID()), str(ULID())
    old = [
        _file(tmp_path, token=old_token, age=2, size=700_000),
        _file(tmp_path, token=old_token, suffix=".json", age=2),
    ]
    young = [
        _file(tmp_path, token=new_token, age=1, size=700_000),
        _file(tmp_path, token=new_token, suffix=".json", age=1),
    ]

    result = _run(db_session)

    assert result["quota_files"] == 2 and result["expired_files"] == 0
    assert not any(path.exists() for path in old)
    assert all(path.exists() for path in young)
    assert capture_queue.status(db_session)["dead_letter"]["bytes"] <= 1024 * 1024


def test_one_file_budget_rotates_past_locked_half_of_same_frame(db_session, tmp_path, monkeypatch):
    capture_queue.set_policy(db_session, {"cleanup_batch_files": 1})
    token = str(ULID())
    enc = _file(tmp_path, token=token, age=8)
    meta = _file(tmp_path, token=token, suffix=".json", age=8)
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path == enc:
            raise PermissionError("synthetic private path must not be returned")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    first = _run(db_session)
    assert first["failed_files"] == 1 and first["budget_exhausted"]
    second = _run(db_session)
    assert second["deleted_files"] == 1 and not meta.exists() and enc.exists()
    monkeypatch.setattr(Path, "unlink", unlink)
    assert _run(db_session)["deleted_files"] == 1 and not enc.exists()


def test_locked_frame_does_not_starve_other_frames(db_session, tmp_path, monkeypatch):
    capture_queue.set_policy(db_session, {"cleanup_batch_files": 1})
    locked_path = _file(tmp_path, age=12)
    later = [_file(tmp_path, age=11), _file(tmp_path, age=10)]
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path == locked_path:
            raise PermissionError("busy")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    assert _run(db_session)["failed_files"] == 1
    for _ in range(3):
        assert _run(db_session)["deleted_files"] <= 1
    assert locked_path.exists() and not any(p.exists() for p in later)


def _restart_scan_cursors():
    for cursor in capture_queue._scan_cursors.values():
        cursor[0].close()
    capture_queue._scan_cursors.clear()


def test_global_quota_converges_when_each_scan_window_is_under_limit(db_session, tmp_path, monkeypatch):
    capture_queue.set_policy(db_session, {"dead_letter_max_bytes": 1024 * 1024})
    paths = [_file(tmp_path, age=1, size=350_000) for _ in range(6)]
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 2)

    first = _run(db_session)
    assert first["quota_files"] == 0 and first["scan_truncated"]
    for _ in range(14):
        _run(db_session)

    assert sum(path.stat().st_size for path in paths if path.exists()) <= 1024 * 1024
    assert any(not path.exists() for path in paths)


def test_quota_discards_partial_cycle_after_restart_and_detects_insertions(db_session, tmp_path, monkeypatch):
    capture_queue.set_policy(db_session, {"dead_letter_max_bytes": 1024 * 1024})
    paths = [_file(tmp_path, age=1, size=350_000) for _ in range(4)]
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 2)
    _run(db_session)
    _restart_scan_cursors()

    after_restart = _run(db_session)
    assert after_restart["quota_files"] == 0  # No double counting the first window.
    paths.append(_file(tmp_path, size=600_000))
    for _ in range(18):
        _run(db_session)
    assert sum(path.stat().st_size for path in paths if path.exists()) <= 1024 * 1024


def test_completed_quota_debt_survives_restart(db_session, tmp_path, monkeypatch):
    capture_queue.set_policy(db_session, {"dead_letter_max_bytes": 1024 * 1024})
    paths = [_file(tmp_path, age=1, size=600_000) for _ in range(3)]
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 1)
    for _ in range(4):
        _run(db_session)
    state = json.loads(db_session.get(Setting, capture_queue.STATUS_KEY).value)
    assert state["quota_deletion_debt_bytes"] > 0
    _restart_scan_cursors()

    result = _run(db_session)
    assert result["quota_files"] == 1
    for _ in range(8):
        _run(db_session)
    assert sum(path.stat().st_size for path in paths if path.exists()) <= 1024 * 1024


def test_complete_fresh_inventory_replaces_stale_quota_debt_after_external_deletion(db_session, tmp_path, monkeypatch):
    capture_queue.set_policy(db_session, {"dead_letter_max_bytes": 1024 * 1024})
    paths = [_file(tmp_path, age=1, size=600_000) for _ in range(3)]
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 1)
    for _ in range(4):
        _run(db_session)
    assert json.loads(db_session.get(Setting, capture_queue.STATUS_KEY).value)["quota_deletion_debt_bytes"] > 0
    paths[0].unlink()
    paths[1].unlink()
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 10_000)

    result = _run(db_session)

    assert result["quota_files"] == 0 and paths[2].exists()
    assert json.loads(db_session.get(Setting, capture_queue.STATUS_KEY).value)["quota_deletion_debt_bytes"] == 0


def test_raising_quota_invalidates_old_debt(db_session, tmp_path, monkeypatch):
    capture_queue.set_policy(db_session, {"dead_letter_max_bytes": 1024 * 1024})
    paths = [_file(tmp_path, age=1, size=600_000) for _ in range(3)]
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 1)
    for _ in range(4):
        _run(db_session)
    capture_queue.set_policy(db_session, {"dead_letter_max_bytes": 2 * 1024 * 1024})
    for _ in range(5):
        assert _run(db_session)["quota_files"] == 0
    assert all(path.exists() for path in paths)


def test_withdrawal_metadata_work_has_separate_bound_and_persists_unvisited_targets(db_session, monkeypatch):
    groups = [str(ULID()) for _ in range(100)]
    db_session.add(Setting(key=capture_queue.WITHDRAWAL_KEY, value=json.dumps({
        "consent_id": str(ULID()), "requested_at": datetime.now(UTC).isoformat(),
        "targets": groups, "remaining_files": 100,
    })))
    db_session.commit()
    visited = []

    def missing(directory, name):
        visited.append((directory, name))
        return None

    monkeypatch.setattr(capture_queue, "MAX_TARGET_STAT_CHECKS", 8)
    monkeypatch.setattr(capture_queue, "_file_stat", missing)
    _run(db_session)
    saved = json.loads(db_session.get(Setting, capture_queue.WITHDRAWAL_KEY).value)
    assert 0 < len(visited) <= 8
    assert 0 < len(saved["targets"]) < len(groups)
    assert saved["remaining_files"] > 0
    assert capture_queue.status(db_session)["withdrawal_cleanup"]["pending"]


@pytest.mark.parametrize("raw", ["{invalid", "{}", "[]", '{"targets":["../outside.enc"]}',
                                 '{"targets":{"name":"private"}}'])
def test_damaged_withdrawal_state_remains_visibly_incomplete(db_session, tmp_path, raw):
    db_session.add(Setting(key=capture_queue.WITHDRAWAL_KEY, value=raw))
    db_session.commit()
    keep = tmp_path / "outside.enc"
    keep.write_bytes(b"keep")
    _run(db_session)
    status = capture_queue.status(db_session)["withdrawal_cleanup"]
    assert status["pending"] and status["inventory_incomplete"]
    assert keep.read_bytes() == b"keep"


def test_bounded_scan_advances_past_locked_prefix(db_session, tmp_path, monkeypatch):
    paths = [_file(tmp_path, age=8) for _ in range(7)]
    locked_paths = set(list((tmp_path / "pending_dead_letter").iterdir())[:2])
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path in locked_paths:
            raise PermissionError("busy")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 2)
    for _ in range(8):
        result = _run(db_session)
        assert result["deleted_files"] <= 2
    assert all(p.exists() == (p in locked_paths) for p in paths)


def test_inventory_reports_truncation_even_when_unrelated_files_consume_budget(db_session, tmp_path, monkeypatch):
    folder = tmp_path / "pending"
    folder.mkdir()
    for i in range(4):
        (folder / f"note-{i}.txt").write_text("keep")
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 2)
    status = capture_queue.status(db_session)
    assert status["pending"]["scan_truncated"]
    assert status["pending"]["files"] == 0
    assert len(list(folder.iterdir())) == 4


def test_cleanup_refuses_symlink_directory_and_generated_file(db_session, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = _file(tmp_path, "outside", age=30)
    (tmp_path / "pending").symlink_to(outside, target_is_directory=True)
    dead = tmp_path / "pending_dead_letter"
    dead.mkdir()
    (dead / f"{ULID()}.enc").symlink_to(victim)
    result = _run(db_session)
    status = capture_queue.status(db_session)
    assert result["deleted_files"] == 0 and result["failed_files"] == 1
    assert status["pending"]["unsafe_files"] == status["dead_letter"]["unsafe_files"] == 1
    assert status["pending"]["scan_truncated"]
    assert victim.read_bytes() == b"x" * 16


def test_missing_queue_status_does_not_create_directories(db_session, tmp_path):
    status = capture_queue.status(db_session)
    assert status["pending"]["files"] == status["dead_letter"]["files"] == 0
    assert not (tmp_path / "pending").exists()
    assert not (tmp_path / "pending_dead_letter").exists()


def test_invalid_persisted_policy_falls_back_and_status_is_allowlisted(db_session):
    db_session.add(Setting(key=capture_queue.POLICY_KEY, value=json.dumps({
        "dead_letter_retention_days": -1, "dead_letter_max_bytes": "secret-path",
        "cleanup_batch_files": True,
    })))
    db_session.add(Setting(key=capture_queue.STATUS_KEY, value=json.dumps({
        "last_run_at": "not a date", "deleted_files": -5, "failed_files": "secret-title",
        "budget_exhausted": "secret-url", "error": "secret-error", "path": "secret-path",
    })))
    db_session.commit()
    status = capture_queue.status(db_session)
    assert status["policy"] == capture_queue.DEFAULT_POLICY
    assert status["cleanup"]["last_run_at"] is None
    assert status["cleanup"]["deleted_files"] == status["cleanup"]["failed_files"] == 0
    assert "secret" not in json.dumps(status)


def test_quarantine_and_failure_after_completed_wipe_do_not_recreate_metadata(tmp_path):
    token = screenshot_async.store_pending(b"frame", {"device_id": "synthetic"})
    screenshot_async.purge_pending_capture_files()
    screenshot_async._quarantine(token, "late classification failure")
    screenshot_async._record_failure(token, RuntimeError("late exception"))
    assert not (tmp_path / "pending" / f"{token}.json").exists()
    assert not (tmp_path / "pending_dead_letter" / f"{token}.json").exists()


@pytest.mark.asyncio
async def test_cleanup_worker_runs_on_startup_before_first_sleep(monkeypatch):
    order = []

    def run_once():
        order.append("cleanup")
        return {}

    async def to_thread(fn):
        return fn()

    async def sleep(interval):
        order.append(("sleep", interval))
        raise asyncio.CancelledError

    monkeypatch.setattr(cleanup_worker, "run_once", run_once)
    monkeypatch.setattr(cleanup_worker.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(cleanup_worker.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await cleanup_worker.loop()
    assert order[0] == "cleanup" and order[1][0] == "sleep"
    assert order[1][1] >= 60


@pytest.mark.asyncio
async def test_cleanup_worker_sleeps_after_failure_and_propagates_cancellation(monkeypatch):
    order = []

    async def failure(_fn):
        order.append("failed")
        raise OSError("synthetic failure")

    async def sleep(_interval):
        order.append("sleep")
        raise asyncio.CancelledError

    monkeypatch.setattr(cleanup_worker.asyncio, "to_thread", failure)
    monkeypatch.setattr(cleanup_worker.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await cleanup_worker.loop()
    assert order == ["failed", "sleep"]
