"""Loopback-only first-device pairing bootstrap for all-in-one installs."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import rate_limit


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    rate_limit._clear_all()
    from app.main import create_app
    from app.db.models import Base
    from app.db.session import get_engine

    Base.metadata.create_all(bind=get_engine())
    return create_app()


_BODY = {"hostname": "family-pc", "platform": "windows", "agent_version": "0.1.0", "local_bootstrap": True}


def test_local_bootstrap_pairs_first_device_from_loopback(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    r = client.post("/api/devices/pair/complete", json=_BODY)
    assert r.status_code == 200
    assert r.json()["device_token"]

    # Second attempt is closed: a device is already paired.
    r = client.post("/api/devices/pair/complete", json=_BODY)
    assert r.status_code == 400
    assert "already paired" in r.json()["detail"]


def test_local_bootstrap_rejected_from_remote_address(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("192.168.1.50", 50000))
    r = client.post("/api/devices/pair/complete", json=_BODY)
    assert r.status_code == 400
    assert "loopback" in r.json()["detail"].lower()


def test_pairing_without_code_and_without_bootstrap_fails(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    r = client.post(
        "/api/devices/pair/complete",
        json={"hostname": "kid-pc", "platform": "windows", "agent_version": "0.1.0"},
    )
    assert r.status_code == 400
