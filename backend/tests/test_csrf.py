"""Browser session mutations require a per-session CSRF token."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path) -> TestClient:
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
    token = ensure_setup_token()
    r = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Parent",
            "password": "correct horse battery",
            "recovery_code": "one two three",
            "setup_token": token,
        },
    )
    assert r.status_code == 200
    return client


def test_session_mutation_requires_csrf_token(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    payload = {
        "critical": 120,
        "high": 90,
        "medium": 30,
        "low": 1,
        "none": 0,
        "screenshots_flagged": 45,
        "audit_logs": 180,
    }

    r = client.patch("/api/settings/retention", json=payload)
    assert r.status_code == 403
    assert "csrf" in r.json()["detail"].lower()

    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    r = client.patch("/api/settings/retention", json=payload, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200


def test_device_endpoints_are_not_browser_csrf_challenged(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    r = client.post("/api/devices/heartbeat", json={"queued_frames": 0})
    assert r.status_code == 401

    r = client.post(
        "/api/devices/pair/complete",
        json={"hostname": "kid-pc", "code": "000000"},
    )
    assert r.status_code == 400
