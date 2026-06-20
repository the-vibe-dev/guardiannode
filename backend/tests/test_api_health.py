"""Smoke test for the FastAPI app."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod
    settings_mod.settings = settings_mod.Settings()
    # Disable mDNS in tests
    settings_mod.settings.mdns_enabled = False
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
