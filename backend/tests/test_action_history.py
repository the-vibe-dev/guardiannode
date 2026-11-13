"""Parent command receipts must distinguish a failed action from no side effect."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import Alert, Device, DeviceCommand, Event, RiskResult, User
from app.db.session import get_sessionmaker
from tests.test_readiness_apis import _client


@pytest.fixture
def action_history(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    now = datetime.now(UTC)
    with get_sessionmaker()() as db:
        parent_id = db.query(User.id).scalar()
        db.add(Device(device_id="action-history-device", hostname="synthetic-pc", paired=True))
        db.flush()
        db.add(Event(event_id="action-history-event", device_id="action-history-device",
                     source_type="system", timestamp=now))
        db.flush()
        db.add(RiskResult(risk_id="action-history-risk", event_id="action-history-event",
                          risk_level="high", score=75))
        db.flush()
        db.add(Alert(alert_id="action-history-alert", risk_id="action-history-risk", severity="high",
                      device_id="action-history-device"))
        db.flush()
        for index in range(55):
            db.add(DeviceCommand(
                command_id=f"history-{index:03}", device_id="action-history-device",
                alert_id="action-history-alert", command_type="pause_app", status="queued",
                payload={"target": r"C:\Games\Game.exe", "duration_seconds": 900},
                preview="Pause synthetic game for 15 minutes", created_at=now,
                created_by=parent_id,
                expires_at=now + timedelta(hours=24),
            ))
        db.commit()
    return client


def test_history_is_bounded_ordered_and_retains_existing_action_fields(action_history):
    response = action_history.get("/api/alerts/action-history-alert/actions")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 50
    assert [row["action_id"] for row in rows] == [f"history-{index:03}" for index in range(54, 4, -1)]
    assert rows[0]["execution"] is None
    assert rows[0]["created_at"] is not None
    assert rows[0]["status"] == "queued"
    assert len(action_history.get("/api/alerts/action-history-alert/actions", params={"limit": 100}).json()) == 55
    assert action_history.get("/api/alerts/action-history-alert/actions", params={"limit": 101}).status_code == 422


def test_failed_but_active_lease_is_visible_without_raw_agent_content(action_history):
    deadline = datetime.now(UTC) + timedelta(minutes=15)
    with get_sessionmaker()() as db:
        command = db.get(DeviceCommand, "history-054")
        command.status = "failed"
        command.completed_at = datetime.now(UTC)
        command.result = {
            "lease_status": "active", "expires_at": deadline.timestamp(),
            "suspended_processes": 2, "failed_processes": 1, "active_pause_leases": 2,
            "pending_resume_processes": 1, "partial_failure": True,
            "retryable": True, "scan_complete": False,
            "error": "private-error-marker", "private": "private-content-marker",
        }
        db.commit()
    response = action_history.get("/api/alerts/action-history-alert/actions")
    row = response.json()[0]
    assert row["status"] == "failed"
    assert row["completed_at"] is not None
    assert row["execution"]["lease_status"] == "active"
    assert row["execution"]["suspended_processes"] == 2
    assert row["execution"]["active_pause_leases"] == 2
    assert row["execution"]["pending_resume_processes"] == 1
    assert row["execution"]["has_error"] is True
    assert row["execution"]["lease_expires_at"].endswith("Z")
    assert "private-" not in response.text


def test_malformed_diagnostic_fields_cannot_break_parent_history(action_history):
    with get_sessionmaker()() as db:
        db.get(DeviceCommand, "history-054").result = {
            "lease_status": [], "expires_at": "not a timestamp", "partial_failure": "true",
            "suspended_processes": True, "failed_processes": -1, "undone": 10**20,
        }
        db.commit()
    response = action_history.get("/api/alerts/action-history-alert/actions")
    assert response.status_code == 200
    execution = response.json()[0]["execution"]
    assert all(execution[field] is None for field in (
        "lease_status", "lease_expires_at", "partial_failure", "suspended_processes", "failed_processes", "undone",
    ))


def test_undo_receipt_links_original_and_rejects_duplicate_requests(action_history):
    response = action_history.post("/api/actions/history-054/undo")
    assert response.status_code == 200
    assert response.json()["undo_of"] == "history-054"
    assert response.json()["status"] == "queued"
    assert action_history.post("/api/actions/history-054/undo").status_code == 409
    rows = action_history.get("/api/alerts/action-history-alert/actions").json()
    undo = next(row for row in rows if row["undo_of"] == "history-054")
    assert undo["action_id"] == response.json()["action_id"]
    assert undo["execution"] is None


def test_history_requires_parent_and_known_alert(action_history):
    assert action_history.get("/api/alerts/missing/actions").status_code == 404
    with get_sessionmaker()() as db:
        db.query(User).first().role = "viewer"
        db.commit()
    assert action_history.get("/api/alerts/action-history-alert/actions").status_code == 403
    assert action_history.post("/api/actions/history-054/undo").status_code == 403
    assert action_history.post("/api/alerts/action-history-alert/actions", json={
        "action": "pause_app", "target": r"C:\Games\Game.exe", "duration_seconds": 900,
    }).status_code == 403
    assert action_history.post("/api/alerts/action-history-alert/action", json={"action": "notify"}).status_code == 403
    assert action_history.post("/api/settings/notifications/test").status_code == 403
    action_history.cookies.clear()
    assert action_history.get("/api/alerts/action-history-alert/actions").status_code == 401
