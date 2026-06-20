"""Pairing-code single-use behavior under concurrent completion."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    from app.main import create_app
    from app.db.models import Base
    from app.db.session import get_engine

    Base.metadata.create_all(bind=get_engine())
    return create_app()


def test_pairing_code_can_only_pair_one_device_concurrently(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    from app.db.models import Device
    from app.db.session import get_sessionmaker
    from app.services import pairing

    s = get_sessionmaker()()
    try:
        code, _expires_at = pairing.issue(s)
        s.commit()
    finally:
        s.close()

    def pair(hostname: str) -> int:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            r = client.post(
                "/api/devices/pair/complete",
                json={
                    "code": code,
                    "hostname": hostname,
                    "platform": "windows",
                    "agent_version": "0.1.0-alpha.1",
                },
            )
            return r.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(pair, ["kid-a", "kid-b"]))

    assert statuses.count(200) == 1
    s = get_sessionmaker()()
    try:
        assert s.query(Device).filter(Device.paired.is_(True)).count() == 1
    finally:
        s.close()
