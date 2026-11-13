"""Notification diagnostics remain bounded and omit content and transport secrets."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db.models import DigestRun, NotificationLog
from app.services.notification_status import delivery_status
from tests.test_notification_reliability import _configure, _job
from tests.test_readiness_apis import _client


def test_status_uses_metadata_allowlists_and_bounded_history(db_session):
    _configure(db_session, host="smtp.example.test", password="private-password-marker", webhook_url="https://example.test/private-token")
    for index in range(25):
        job = _job(db_session, f"status-{index:02}")
        job.status = "retry" if index % 2 else "sent"
        job.last_error = "private-error-marker"
        job.risk_summary = "private-evidence-marker"
        job.delivered_channels = ["email"]
        db_session.add(NotificationLog(
            alert_id=job.alert_id, channel="email", severity="high", result="ok",
            detail="private-transport-marker", created_at=datetime.now(UTC),
        ))
    db_session.add(DigestRun(
        digest_id="digest-status", local_date="2026-11-10", timezone="America/New_York",
        status="sent", summary={"total": 25, "top": [{"summary": "private-digest-marker"}]},
    ))
    db_session.commit()
    result = delivery_status(db_session)
    assert result["counts"]["retry"] == 12
    assert result["counts"]["sent"] == 13
    assert len(result["recent_jobs"]) == len(result["recent_attempts"]) == 20
    assert result["channels"]["email"]["last_success_at"].endswith("+00:00")
    assert result["last_digest"]["total_alerts"] == 25
    assert "private-" not in json.dumps(result)
    assert "password" not in json.dumps(result)
    assert "webhook_url" not in json.dumps(result)


def test_status_endpoint_requires_parent_auth_and_never_sends(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    from app.services import notifications
    monkeypatch.setattr(notifications, "_send_email", lambda *args: (_ for _ in ()).throw(AssertionError("Read-only status attempted send")))
    response = client.get("/api/settings/notifications/status")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["recent_jobs"] == []
    client.cookies.clear()
    assert client.get("/api/settings/notifications/status").status_code == 401
