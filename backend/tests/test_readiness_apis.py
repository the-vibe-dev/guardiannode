from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.models import ChildProfile, Device
from app.services import event_ingest


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    from app.main import create_app
    from app.db.models import Base
    from app.db.session import get_engine
    from app.services.setup_token import ensure_setup_token

    Base.metadata.create_all(bind=get_engine())
    client = TestClient(create_app())
    setup_token = ensure_setup_token()
    r = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Parent",
            "password": "correct horse",
            "recovery_code": "one two three",
            "setup_token": setup_token,
        },
    )
    assert r.status_code == 200
    return client


def test_settings_audit_and_storage_endpoints(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    r = client.get("/api/settings/notifications")
    assert r.status_code == 200
    assert r.json()["password_configured"] is False

    r = client.patch(
        "/api/settings/notifications",
        json={
            "enabled": True,
            "host": "smtp.test.invalid",
            "port": 587,
            "tls_mode": "starttls",
            "username": "parent",
            "password": "secret",
            "from_address": "guardian@example.test",
            "to_address": "parent@example.test",
            "webhook_url": "",
            "immediate_min_severity": "high",
            "daily_digest_enabled": True,
            "daily_digest_time": "08:00",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["password"] is None
    assert body["password_configured"] is True

    r = client.patch(
        "/api/settings/notifications",
        json={
            "enabled": True,
            "host": "smtp.test.invalid",
            "port": 587,
            "tls_mode": "starttls",
            "username": "parent",
            "password": "",
            "from_address": "guardian@example.test",
            "to_address": "new-parent@example.test",
            "webhook_url": "",
            "immediate_min_severity": "high",
            "daily_digest_enabled": True,
            "daily_digest_time": "08:00",
        },
    )
    assert r.status_code == 200
    assert r.json()["password_configured"] is True

    r = client.patch(
        "/api/settings/notifications",
        json={
            "enabled": True,
            "host": "smtp.test.invalid",
            "port": 587,
            "tls_mode": "starttls",
            "username": "parent",
            "clear_password": True,
            "from_address": "guardian@example.test",
            "to_address": "new-parent@example.test",
            "webhook_url": "",
            "immediate_min_severity": "high",
            "daily_digest_enabled": True,
            "daily_digest_time": "08:00",
        },
    )
    assert r.status_code == 200
    assert r.json()["password_configured"] is False

    r = client.patch(
        "/api/settings/retention",
        json={
            "critical": 120,
            "high": 90,
            "medium": 30,
            "low": 1,
            "none": 0,
            "screenshots_flagged": 45,
            "audit_logs": 180,
        },
    )
    assert r.status_code == 200
    assert r.json()["critical"] == 120

    assert client.get("/api/storage").status_code == 200
    audit = client.get("/api/audit").json()
    assert any(row["action"] == "settings.notifications.update" for row in audit)
    assert any(row["action"] == "settings.retention.update" for row in audit)


def test_profile_delete_refuses_referenced_profile(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    r = client.post(
        "/api/profiles",
        json={"display_name": "Kid", "age_group": "10_13", "custom_watch_phrases": []},
    )
    assert r.status_code == 200
    profile_id = r.json()["profile_id"]

    from app.db.session import get_sessionmaker

    s = get_sessionmaker()()
    s.add(
        Device(
            device_id="device-1",
            hostname="kidpc",
            platform="windows",
            paired=True,
            profile_id=profile_id,
        )
    )
    s.commit()
    s.close()

    r = client.delete(f"/api/profiles/{profile_id}")
    assert r.status_code == 409
    assert r.json()["detail"]["references"]["devices"] == 1


@pytest.mark.asyncio
async def test_text_event_passes_profile_custom_watch_phrases(db_session, monkeypatch):
    db_session.add(
        Device(
            device_id="device-1",
            hostname="kidpc",
            platform="windows",
            agent_version="0.1.0-alpha.1",
            paired=True,
            status="online",
            profile_id="child-1",
        )
    )
    db_session.add(
        ChildProfile(
            profile_id="child-1",
            display_name="Kid",
            age_group="10_13",
            custom_watch_phrases=["Example Middle School"],
        )
    )
    db_session.commit()

    async def fake_classify_text(**kwargs):
        assert kwargs["custom_phrases"] == ["Example Middle School"]
        return {
            "risk_level": "high",
            "score": 75,
            "categories": ["custom_watch"],
            "summary": "Detected parent watch phrase.",
            "evidence": ["Example Middle School"],
            "recommended_action": "alert_parent",
            "model": None,
            "rules_triggered": ["custom_watch:example middle school"],
            "confidence": 0.95,
            "false_positive_notes": "",
            "prompt_version": "test",
            "rules_version": "test",
        }

    monkeypatch.setattr(event_ingest.classifier, "classify_text", fake_classify_text)
    result = await event_ingest.ingest_event(
        db_session,
        payload={
            "profile_id": "child-1",
            "source_type": "browser",
            "redacted_text": "I go to Example Middle School",
            "capture_scope": "browser_dom",
        },
        device_id="device-1",
    )

    assert result["risk_level"] == "high"
    assert result["categories"] == ["custom_watch"]
