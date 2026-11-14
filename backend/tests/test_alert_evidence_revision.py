"""Parent review decisions are bound to the occurrence displayed in the UI."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import Alert, AuditLog, Event, GuardianReviewPreview, RiskResult
from app.db.session import get_sessionmaker
from app.services.alert_dedup import dedup_key, upsert_alert
from tests.test_guardian_review import _client


def _repeat_incident():
    """A fresh screenshot advances the existing open alert while it is viewed."""
    with get_sessionmaker()() as db:
        alert = db.get(Alert, "alert-1")
        alert.dedup_key = dedup_key("device-1", "profile-1", "high", ["grooming"], "screenshot")
        db.add(Event(
            event_id="event-2", device_id="device-1", profile_id="profile-1", source_type="image",
            timestamp=datetime.now(UTC),
        ))
        db.flush()
        db.add(RiskResult(
            risk_id="risk-2", event_id="event-2", risk_level="high", score=82,
            categories=["grooming"], summary="Newer synthetic occurrence.",
            evidence=["A different synthetic message"], classifier_status="ok",
        ))
        db.flush()
        alert_id, created = upsert_alert(
            db, risk_id="risk-2", device_id="device-1", profile_id="profile-1",
            severity="high", categories=["grooming"], source="screenshot",
        )
        assert alert_id == "alert-1" and created is False
        db.commit()


@pytest.mark.parametrize("endpoint,payload,audit_action", [
    ("review", {"status": "reviewed", "notes": "Parent saw the first occurrence"}, "alert.review"),
    ("feedback", {"feedback_type": "false_positive", "notes": "Parent saw the first occurrence"}, "alert.feedback"),
    ("action", {"action": "escalate"}, "alert.action"),
    ("actions", {"action": "delete_evidence"}, "alert.action.confirmed"),
])
def test_stale_review_feedback_escalation_and_deletion_have_no_side_effects(monkeypatch, tmp_path, endpoint, payload, audit_action):
    client = _client(monkeypatch, tmp_path)
    detail = client.get("/api/alerts/alert-1").json()
    request = {**payload, "expected_risk_id": detail["alert"]["risk_id"]}
    if endpoint == "actions":
        confirmation = client.post("/api/alerts/alert-1/actions", json=request)
        assert confirmation.status_code == 409
        request["confirmed_preview"] = confirmation.json()["detail"]["preview"]

    _repeat_incident()
    rejected = client.post(f"/api/alerts/alert-1/{endpoint}", json=request)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "evidence_changed"
    with get_sessionmaker()() as db:
        assert db.get(Alert, "alert-1").status == "open"
        assert db.get(Alert, "alert-1").notes is None
        assert not db.get(RiskResult, "risk-2").false_positive_notes
        assert db.get(Event, "event-1").deletion_state == "active"
        assert db.get(Event, "event-2").deletion_state == "active"
        assert db.query(AuditLog).filter(AuditLog.action == audit_action).count() == 0

    # A subsequent explicit decision using the refreshed evidence still works.
    request["expected_risk_id"] = "risk-2"
    accepted = client.post(f"/api/alerts/alert-1/{endpoint}", json=request)
    assert accepted.status_code == 200, accepted.text
    with get_sessionmaker()() as db:
        assert db.query(AuditLog).filter(AuditLog.action == audit_action).count() == 1
        if endpoint == "feedback":
            assert "Parent saw" in db.get(RiskResult, "risk-2").false_positive_notes
            assert not db.get(RiskResult, "risk-1").false_positive_notes
        if endpoint == "actions":
            assert db.get(Event, "event-2") is None
            assert db.get(Event, "event-1").deletion_state == "active"


def test_guardian_preview_cannot_reuse_selected_ids_from_replaced_evidence(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    request = {"expected_risk_id": "risk-1", "selected_evidence_ids": ["risk:0"]}
    first = client.post("/api/alerts/alert-1/guardian-review/preview", json=request)
    assert first.status_code == 200
    assert "expected_risk_id" not in str(first.json()["outbound_payload"])

    _repeat_incident()
    rejected = client.post("/api/alerts/alert-1/guardian-review/preview", json=request)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "evidence_changed"
    with get_sessionmaker()() as db:
        assert db.query(GuardianReviewPreview).count() == 1

    request["expected_risk_id"] = "risk-2"
    refreshed = client.post("/api/alerts/alert-1/guardian-review/preview", json=request)
    assert refreshed.status_code == 200, refreshed.text
    assert "different synthetic message" in str(refreshed.json()["outbound_payload"])
