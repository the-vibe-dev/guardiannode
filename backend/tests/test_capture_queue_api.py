from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import settings as settings_mod
from app.db.models import AuditLog, Device, Setting, User
from app.db.session import get_sessionmaker
from app.services import capture_queue, screenshot_async
from app.workers import cleanup_worker
from tests.test_capture_queue_housekeeping import _file, _restart_scan_cursors
from tests.test_consent_enforcement import _client, _grant
from tests.test_input_bounds import _paired_token


def test_parent_queue_api_has_safe_defaults_and_content_free_inventory(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    token = screenshot_async.store_pending(b"private image", {
        "device_id": "private-device", "window_title": "private title",
        "url": "https://private.example.test", "last_error": "private exception",
    })
    response = client.get("/api/storage/capture-queue")
    assert response.status_code == 200
    status = response.json()
    assert status["policy"] == capture_queue.DEFAULT_POLICY
    assert status["pending"]["files"] == 2 and status["pending"]["frames"] == 1
    assert not status["pending"]["scan_truncated"]
    assert token not in response.text and "private" not in response.text
    assert status["cleanup"]["last_run_at"] is None
    assert not status["withdrawal_cleanup"]["pending"]


def test_queue_policy_patch_is_partial_persistent_and_audited(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    result = client.patch("/api/storage/capture-queue", json={"dead_letter_retention_days": 2})
    assert result.status_code == 200
    assert result.json()["policy"] == {**capture_queue.DEFAULT_POLICY, "dead_letter_retention_days": 2}
    assert client.get("/api/storage/capture-queue").json()["policy"]["dead_letter_retention_days"] == 2
    with get_sessionmaker()() as db:
        row = db.query(AuditLog).filter_by(action="storage.capture_queue.policy").one()
        assert row.details == result.json()["policy"]


@pytest.mark.parametrize("payload", [
    {}, {"cleanup_batch_files": None}, {"cleanup_batch_files": True}, {"cleanup_batch_files": "3"},
    {"cleanup_batch_files": 0}, {"cleanup_batch_files": 1001},
    {"dead_letter_retention_days": 91}, {"dead_letter_retention_days": 0},
    {"dead_letter_max_bytes": 1048575}, {"dead_letter_max_bytes": 4294967297},
    {"unknown": 1},
])
def test_queue_policy_rejects_invalid_or_unknown_fields(monkeypatch, tmp_path, payload):
    client = _client(monkeypatch, tmp_path)
    assert client.patch("/api/storage/capture-queue", json=payload).status_code == 422


def test_queue_endpoints_require_parent_role_and_mutations_require_recent_auth(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    anonymous = TestClient(client.app)
    assert anonymous.get("/api/storage/capture-queue").status_code == 401
    with get_sessionmaker()() as db:
        db.query(User).first().role = "child"
        db.commit()
    assert client.get("/api/storage/capture-queue").status_code == 403
    assert client.patch("/api/storage/capture-queue", json={"cleanup_batch_files": 4}).status_code == 403
    assert client.post("/api/storage/capture-queue/cleanup").status_code == 403
    assert client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"}).status_code == 403
    with get_sessionmaker()() as db:
        db.query(User).first().role = "admin"
        db.commit()
    monkeypatch.setattr(settings_mod.settings, "recent_auth_timeout_seconds", 0)
    assert client.get("/api/storage/capture-queue").status_code == 200
    assert client.patch("/api/storage/capture-queue", json={"cleanup_batch_files": 4}).status_code == 403
    assert client.post("/api/storage/capture-queue/cleanup").status_code == 403


def test_manual_cleanup_applies_ttl_and_returns_updated_status(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    expired = _file(tmp_path, age=9)
    pending = _file(tmp_path, "pending", age=9)
    response = client.post("/api/storage/capture-queue/cleanup")
    assert response.status_code == 200
    status = response.json()
    assert status["cleanup"]["deleted_files"] == status["cleanup"]["expired_files"] == 1
    assert status["dead_letter"]["files"] == 0 and status["pending"]["files"] == 1
    assert not expired.exists() and pending.exists()


def test_withdrawal_intent_survives_crash_before_unlink_and_worker_retries(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    _paired_token(client)
    token = screenshot_async.store_pending(b"synthetic", {"device_id": "synthetic"})
    retry = capture_queue.retry_withdrawal_cleanup

    def crash(_db):
        with get_sessionmaker()() as check:
            assert check.get(Setting, capture_queue.WITHDRAWAL_KEY) is not None
            assert all(not device.paired and device.token_hash is None for device in check.query(Device))
        raise RuntimeError("simulated crash after committed revocation")

    monkeypatch.setattr(capture_queue, "retry_withdrawal_cleanup", crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    assert (tmp_path / "pending" / f"{token}.enc").exists()
    monkeypatch.setattr(capture_queue, "retry_withdrawal_cleanup", retry)
    _restart_scan_cursors()

    result = cleanup_worker.run_once()

    assert result["queue_files"] == 2
    assert not (tmp_path / "pending" / f"{token}.enc").exists()
    status = client.get("/api/storage/capture-queue").json()["withdrawal_cleanup"]
    assert not status["pending"] and status["remaining_files"] == 0


def test_locked_withdrawal_retries_after_new_consent_without_deleting_new_capture(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    old = screenshot_async.store_pending(b"old frame", {"device_id": "old-device"})
    locked_path = tmp_path / "pending" / f"{old}.enc"
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path == locked_path:
            raise PermissionError("synthetic locked image")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    result = client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    assert result.json()["deletion"]["pending_captures"] == {"deleted": 1, "failed": 1}
    _grant(client)
    new = screenshot_async.store_pending(b"new authorized frame", {"device_id": "new-device"})
    monkeypatch.setattr(Path, "unlink", unlink)
    _restart_scan_cursors()

    retried = client.post("/api/storage/capture-queue/cleanup")

    assert retried.status_code == 200
    assert not retried.json()["withdrawal_cleanup"]["pending"]
    assert not locked_path.exists()
    assert (tmp_path / "pending" / f"{new}.enc").exists()
    assert (tmp_path / "pending" / f"{new}.json").exists()


def test_withdrawal_target_follows_frame_moved_to_quarantine(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    old = screenshot_async.store_pending(b"old frame", {"device_id": "old-device"})
    locked_path = tmp_path / "pending" / f"{old}.enc"
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path == locked_path:
            raise PermissionError("locked")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    _grant(client)
    screenshot_async._quarantine(old, "old orphan after worker restart")
    monkeypatch.setattr(Path, "unlink", unlink)
    assert (tmp_path / "pending_dead_letter" / f"{old}.enc").exists()
    result = client.post("/api/storage/capture-queue/cleanup").json()
    assert result["cleanup"]["deleted_files"] == 2
    assert not result["withdrawal_cleanup"]["pending"]
    assert not (tmp_path / "pending_dead_letter" / f"{old}.json").exists()


def test_truncated_withdrawal_stays_incomplete_after_regrant_and_preserves_new_frame(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    for _ in range(3):
        screenshot_async.store_pending(b"old frame", {"device_id": "old-device"})
    monkeypatch.setattr(capture_queue, "MAX_SCAN_ENTRIES", 1)
    client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    _grant(client)
    new = screenshot_async.store_pending(b"new authorized frame", {"device_id": "new-device"})
    for _ in range(3):
        result = client.post("/api/storage/capture-queue/cleanup").json()
    assert result["withdrawal_cleanup"]["pending"]
    assert result["withdrawal_cleanup"]["inventory_incomplete"]
    assert (tmp_path / "pending" / f"{new}.enc").exists()


def test_withdraw_and_retain_never_creates_capture_deletion_request(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    token = screenshot_async.store_pending(b"retained frame", {"device_id": "synthetic"})
    assert client.post("/api/consent/withdraw", json={"evidence_disposition": "retain"}).status_code == 200
    cleanup_worker.run_once()
    assert (tmp_path / "pending" / f"{token}.enc").exists()
    with get_sessionmaker()() as db:
        assert db.get(Setting, capture_queue.WITHDRAWAL_KEY) is None


def test_unlinked_file_then_transaction_rollback_finishes_without_recreating_data(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    token = screenshot_async.store_pending(b"old frame", {"device_id": "synthetic"})
    retry = capture_queue.retry_withdrawal_cleanup

    def delete_then_rollback(db):
        result = retry(db)
        db.rollback()  # Simulate process loss after unlink but before progress commit.
        return result

    monkeypatch.setattr(capture_queue, "retry_withdrawal_cleanup", delete_then_rollback)
    client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    monkeypatch.setattr(capture_queue, "retry_withdrawal_cleanup", retry)
    with get_sessionmaker()() as db:
        assert json.loads(db.get(Setting, capture_queue.WITHDRAWAL_KEY).value)["targets"]
    cleanup_worker.run_once()
    screenshot_async._quarantine(token, "stale worker")
    assert not (tmp_path / "pending_dead_letter" / f"{token}.json").exists()
    assert not client.get("/api/storage/capture-queue").json()["withdrawal_cleanup"]["pending"]
