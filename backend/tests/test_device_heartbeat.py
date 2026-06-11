"""Device heartbeat: liveness + agent upload-backlog reporting."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import pipeline_metrics, rate_limit


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    rate_limit._clear_all()
    pipeline_metrics.reset_for_tests()
    from app.main import create_app
    from app.db.models import Base
    from app.db.session import get_engine

    Base.metadata.create_all(bind=get_engine())
    return TestClient(create_app(), client=("127.0.0.1", 50000))


def test_heartbeat_reports_backlog_and_updates_last_seen(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    r = client.post(
        "/api/devices/pair/complete",
        json={"hostname": "kid-pc", "platform": "windows", "agent_version": "0.1.0", "local_bootstrap": True},
    )
    assert r.status_code == 200
    token = r.json()["device_token"]

    r = client.post(
        "/api/devices/heartbeat",
        json={"queued_frames": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    queues = pipeline_metrics.agent_queues()
    assert len(queues) == 1
    assert queues[0]["hostname"] == "kid-pc"
    assert queues[0]["queued_frames"] == 7

    # Unauthenticated heartbeats are rejected.
    r = client.post("/api/devices/heartbeat", json={"queued_frames": 1})
    assert r.status_code == 401
