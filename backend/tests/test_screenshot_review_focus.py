"""The product reviews screenshots; legacy device restrictions cannot return."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, Request

from app.api.child_requests import ChildRequestCreate, create_child_request
from app.api.devices import claim_commands
from app.api.policies import DEFAULT_POLICY_CONFIG
from app.db.models import (
    Alert,
    ChildProfile,
    ChildRequest,
    Device,
    DeviceCommand,
    Event,
    EvidenceBlob,
    Policy,
    RiskResult,
    User,
)
from app.db.session import get_sessionmaker
from app.services import multimodal_risk, pipeline_metrics, profile_policy, taxonomy
from app.services.evidence_paths import evidence_blob_path
from tests.test_readiness_apis import _client


def test_old_queued_and_claimed_restrictions_are_rejected_but_undo_delivers(db_session):
    user = User(display_name="Parent", password_hash="test", recovery_hash="test")
    device = Device(device_id="device", hostname="synthetic", paired=True)
    other = Device(device_id="other", hostname="other", paired=True)
    db_session.add_all([user, device, other])
    db_session.flush()
    now = datetime.now(UTC)
    for index, action in enumerate(("pause_app", "block_domain", "block_app", "show_child_prompt", "unknown_action", "undo_action")):
        db_session.add(DeviceCommand(
            command_id=f"command-{index}", device_id=device.device_id,
            command_type=action, preview="Synthetic historic action", created_by=user.id,
            status="claimed" if index % 2 == 0 else "queued",
            claimed_at=now - timedelta(hours=1), expires_at=now + timedelta(hours=1),
        ))
    db_session.add(DeviceCommand(
        command_id="other-command", device_id=other.device_id, command_type="pause_app",
        preview="Other device", created_by=user.id, expires_at=now + timedelta(hours=1),
    ))
    db_session.commit()

    claimed = claim_commands(db_session, device)

    assert [row.command_type for row in claimed] == ["undo_action"]
    for index in range(5):
        row = db_session.get(DeviceCommand, f"command-{index}")
        assert row.status == "rejected"
        assert row.completed_at is not None
        assert row.result == {"error": "retired_product_capability", "retryable": False}
    assert db_session.get(DeviceCommand, "other-command").status == "queued"


def test_new_exception_requests_return_gone_without_persisting(db_session):
    device = Device(device_id="device", hostname="synthetic", paired=True)
    db_session.add(device)
    db_session.commit()
    request = Request({"type": "http", "method": "POST", "path": "/api/child-requests", "headers": []})
    with pytest.raises(HTTPException) as result:
        create_child_request(ChildRequestCreate(request_type="more_time"), request, db_session, device)
    assert result.value.status_code == 410
    assert db_session.query(ChildRequest).count() == 0


def test_policy_reads_remove_legacy_restrictions_and_writes_reject_them(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with get_sessionmaker()() as db:
        db.add(ChildProfile(profile_id="child", display_name="Child", age_group="10_13"))
        db.flush()
        db.add(Policy(policy_id="legacy", profile_id="child", config_json={
            **DEFAULT_POLICY_CONFIG, "enforcement": {"on_high": ["block_app"]},
            "schedule": {"enabled": True, "windows": ["bedtime"]}, "screen_time_minutes": 30,
        }))
        db.commit()
    effective = client.get("/api/policies/child/effective").json()["config"]
    assert set(effective) == {"monitored_apps", "monitored_domains", "capture", "severity_thresholds"}
    for endpoint, method in (("/api/policies", client.post), ("/api/policies/legacy", client.patch), ("/api/policies/child/effective", client.patch)):
        response = method(endpoint, json={"profile_id": "child", "config": {"schedule": {"enabled": True}}})
        assert response.status_code == 422
    assert client.patch("/api/policies/legacy", json={"config": DEFAULT_POLICY_CONFIG}).status_code == 200


@pytest.mark.parametrize("action", ["pause_app", "block_app", "block_domain"])
def test_model_restriction_suggestions_become_parent_review(action):
    result = taxonomy.normalize_model_output({"risk_level": "high", "recommended_action": action})
    assert result["recommended_action"] == "alert_parent"
    merged = multimodal_risk.merge(text_result={"recommended_action": action}, vision_result=None)
    assert merged["recommended_action"] == "alert_parent"


def test_legacy_category_modes_normalize_to_review_without_restrictions():
    policy = profile_policy.normalize({"categories": {
        "bullying": {"mode": "block", "min_severity": "high"},
        "scam": {"mode": ["hostile"], "min_severity": {}},
    }})
    assert policy["categories"]["bullying"] == {"mode": "alert", "min_severity": "high"}
    assert policy["categories"]["scam"] == {"mode": "alert", "min_severity": None}


def test_malformed_capture_configuration_cannot_break_device_review_settings(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    profile = client.post("/api/profiles", json={"display_name": "Child", "age_group": "10_13"}).json()
    profile_id = profile["profile_id"]
    for capture in ({"level": []}, {"cadence_seconds": True}, {"cadence_seconds": 0}, {"phash_threshold": 1000}, {"max_capture_interval_seconds": "60"}, {"full_screen_capture_enabled": "false"}):
        response = client.patch(f"/api/profiles/{profile_id}", json={"alert_policy": {"capture": capture}})
        assert response.status_code == 422
    for config in ({"capture": []}, {"capture": {"scope": "block_apps"}}, {"capture": {"cadence_seconds": -5}}, {"monitored_apps": "all"}, {"severity_thresholds": {"alert_at": []}}):
        response = client.post("/api/policies", json={"profile_id": profile_id, "config": config})
        assert response.status_code == 422
    response = client.patch(f"/api/profiles/{profile_id}", json={"alert_policy": {
        "capture": {"level": "balanced", "cadence_seconds": 10, "max_capture_interval_seconds": 60},
    }})
    assert response.status_code == 200
    assert profile_policy.capture_settings(response.json()["alert_policy"])["cadence_seconds"] == 10
    recovered = profile_policy.capture_settings({"min_severity": [], "capture": {
        "level": [], "cadence_seconds": -100, "max_capture_interval_seconds": "bad",
        "full_screen_capture_enabled": "false",
    }})
    assert recovered["level"] == "balanced"
    assert recovered["cadence_seconds"] == 8
    assert recovered["max_capture_interval_seconds"] == 120
    assert recovered["full_screen_capture_enabled"] is True


def test_pipeline_failure_is_not_reported_as_a_successful_safe_review():
    pipeline_metrics.reset_for_tests()
    try:
        pipeline_metrics.start(event_id="failed", tier="vision_only", device_id="device")
        pipeline_metrics.finish("failed", severity="none", succeeded=False)
        snapshot = pipeline_metrics.snapshot(window_seconds=300)
        assert snapshot["failed_frames_in_window"] == 1
        assert snapshot["throughput"]["frames_in_window"] == 0
        assert snapshot["throughput"]["severity_counts"] == {}
        assert snapshot["last_classified_at"] is None
        assert snapshot["in_flight_count"] == 0
    finally:
        pipeline_metrics.reset_for_tests()


def _seed_alert(db, *, level="low", source="image"):
    now = datetime.now(UTC)
    db.add(Device(device_id="evidence-device", hostname="synthetic", paired=True))
    db.flush()
    event = Event(event_id="evidence-event", device_id="evidence-device", source_type=source, timestamp=now)
    db.add(event)
    db.flush()
    db.add(RiskResult(risk_id="evidence-risk", event_id=event.event_id, risk_level=level, score=10, classifier_status="unclassified_model_unavailable"))
    db.flush()
    db.add(Alert(alert_id="evidence-alert", risk_id="evidence-risk", severity=level, device_id="evidence-device"))
    db.commit()
    return event


def test_screenshot_availability_uses_evidence_not_severity_and_hides_paths(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    path = evidence_blob_path("focus-blob")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic encrypted bytes")
    with get_sessionmaker()() as db:
        event = _seed_alert(db)
        event.screenshot_blob_id = "focus-blob"
        db.add(EvidenceBlob(blob_id="focus-blob", kind="screenshot", encrypted_path=str(path), mime_type="image/jpeg", size_bytes=25, event_id=event.event_id))
        db.commit()
    response = client.get("/api/alerts/evidence-alert")
    assert response.status_code == 200
    assert response.json()["event"]["has_screenshot"] is True
    assert response.json()["event"]["screenshot_status"] == "available"
    assert response.json()["risk"]["classifier_status"] == "unclassified_model_unavailable"
    assert str(path) not in response.text
    path.unlink()
    assert client.get("/api/alerts/evidence-alert").json()["event"]["screenshot_status"] == "missing"
    with get_sessionmaker()() as db:
        db.get(EvidenceBlob, "focus-blob").deletion_state = "pending_delete"
        db.commit()
    event = client.get("/api/alerts/evidence-alert").json()["event"]
    assert event["has_screenshot"] is False
    assert event["screenshot_status"] == "pending_delete"


def test_high_text_alert_never_promises_a_screenshot_and_delete_still_works(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with get_sessionmaker()() as db:
        _seed_alert(db, level="high", source="text")
    event = client.get("/api/alerts/evidence-alert").json()["event"]
    assert event["has_screenshot"] is False
    assert event["screenshot_status"] == "not_retained"
    preview = client.post("/api/alerts/evidence-alert/actions", json={"action": "delete_evidence"})
    assert preview.status_code == 409
    result = client.post("/api/alerts/evidence-alert/actions", json={
        "action": "delete_evidence", "confirmed_preview": preview.json()["detail"]["preview"],
    })
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert client.get("/api/alerts/evidence-alert").status_code == 404
