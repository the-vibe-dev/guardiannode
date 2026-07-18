from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.models import Alert, AuditLog, Event, GuardianReview, User
from app.demo_scenarios import SCENARIOS
from app.services import guardian_review


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings(
        demo_mode_enabled=True,
        guardian_review_enabled=True,
        guardian_review_provider="mock",
        mdns_enabled=False,
        retention_cleanup_enabled=False,
        device_offline_alert_enabled=False,
        notification_worker_enabled=False,
        database_backup_enabled=False,
    )
    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app
    from app.services.setup_token import ensure_setup_token

    Base.metadata.create_all(bind=get_engine())
    client = TestClient(create_app())
    response = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Demo Parent",
            "password": "correct horse battery",
            "recovery_code": "one two three",
            "setup_token": ensure_setup_token(),
        },
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]})
    return client


def test_all_synthetic_scenarios_use_local_classifier_and_are_resettable(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/api/demo/status").json()["guardian_review"]["ready"] is True
    listed = client.get("/api/demo/scenarios")
    assert listed.status_code == 200
    assert len(listed.json()) == 6
    assert all("text" not in row for row in listed.json())

    alerts: list[str] = []
    for scenario in SCENARIOS:
        response = client.post(f"/api/demo/scenarios/{scenario['id']}/trigger")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["synthetic"] is True
        assert body["local_detection"]["severity"] == scenario["expected_local_severity"]
        alerts.append(body["alert_id"])

    detail = client.get(f"/api/alerts/{alerts[0]}")
    assert detail.status_code == 200
    assert detail.json()["synthetic"] is True
    assert detail.json()["demo_context"]["scenario_id"] == SCENARIOS[0]["id"]

    preview = client.post(
        f"/api/alerts/{alerts[0]}/guardian-review/preview",
        json={
            "relationship_context": SCENARIOS[0]["relationship_context"],
            "repeated_behavior": SCENARIOS[0]["repeated_behavior"],
            "parent_goal": SCENARIOS[0]["parent_goal"],
        },
    ).json()
    submitted = client.post(
        f"/api/alerts/{alerts[0]}/guardian-review",
        json={
            "preview_id": preview["preview_id"],
            "preview_digest": preview["preview_digest"],
            "consent": True,
        },
    )
    assert submitted.status_code == 202
    from app.db.session import get_sessionmaker

    db = get_sessionmaker()()
    try:
        asyncio.run(guardian_review.process_one(db))
    finally:
        db.close()
    result = client.get(submitted.json()["status_url"])
    assert result.json()["status"] == "completed"
    assert result.json()["assessment"]["schema_version"] == "1.1.0"

    reset = client.post("/api/demo/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["alerts_removed"] == 6
    db = get_sessionmaker()()
    try:
        assert db.query(Event).filter(Event.event_id.like("demo-event-%")).count() == 0
        assert db.query(Alert).filter(Alert.alert_id.like("demo-alert-%")).count() == 0
        assert db.query(GuardianReview).count() == 0
        assert db.query(AuditLog).filter(AuditLog.action == "demo.reset").count() == 1
    finally:
        db.close()


def test_demo_requires_configuration_and_parent_authorization(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.post("/api/demo/scenarios/not-a-scenario/trigger").status_code == 404
    from app.db.session import get_sessionmaker

    db = get_sessionmaker()()
    try:
        db.query(User).filter(User.display_name == "Demo Parent").one().role = "viewer"
        db.commit()
    finally:
        db.close()
    assert client.get("/api/demo/scenarios").status_code == 403
    assert client.post(f"/api/demo/scenarios/{SCENARIOS[0]['id']}/trigger").status_code == 403
    assert client.post("/api/demo/reset").status_code == 403
