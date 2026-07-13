"""Loopback-only first-device pairing bootstrap for all-in-one installs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.services import rate_limit


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    rate_limit._clear_all()
    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app

    Base.metadata.create_all(bind=get_engine())
    return create_app()


_BODY = {"hostname": "family-pc", "platform": "windows", "agent_version": "0.1.0-alpha.1"}


def _body_with_device_token() -> dict:
    from app.services.device_bootstrap_token import ensure_device_bootstrap_token

    return {**_BODY, "device_bootstrap_token": ensure_device_bootstrap_token()}


def test_local_bootstrap_pairs_first_device_from_loopback(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    body = _body_with_device_token()
    r = client.post("/api/devices/bootstrap-local", json=body)
    assert r.status_code == 200
    assert r.json()["device_token"]

    # Second attempt is closed: a device is already paired.
    r = client.post("/api/devices/bootstrap-local", json=body)
    assert r.status_code == 400
    assert "already paired" in r.json()["detail"]


def test_local_bootstrap_rejected_from_remote_address(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("192.168.1.50", 50000))
    r = client.post("/api/devices/bootstrap-local", json=_body_with_device_token())
    assert r.status_code == 400
    assert "loopback" in r.json()["detail"].lower()


def test_local_bootstrap_rejected_without_device_bootstrap_token(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    r = client.post("/api/devices/bootstrap-local", json=_BODY)
    assert r.status_code == 422


def test_local_bootstrap_rejects_admin_setup_token(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    from app.services.setup_token import ensure_setup_token

    r = client.post(
        "/api/devices/bootstrap-local",
        json={**_BODY, "device_bootstrap_token": ensure_setup_token()},
    )
    assert r.status_code == 401


def test_device_bootstrap_token_is_single_use(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    body = _body_with_device_token()

    r = client.post("/api/devices/bootstrap-local", json=body)
    assert r.status_code == 200

    from app.db.models import Device
    from app.db.session import get_sessionmaker

    s = get_sessionmaker()()
    try:
        s.query(Device).delete()
        s.commit()
    finally:
        s.close()

    r = client.post("/api/devices/bootstrap-local", json=body)
    assert r.status_code == 401


def test_device_bootstrap_token_creation_is_concurrency_safe(monkeypatch, tmp_path):
    _app(monkeypatch, tmp_path)
    from app.services.device_bootstrap_token import ensure_device_bootstrap_token, token_path

    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(lambda _: ensure_device_bootstrap_token(), range(8)))

    assert all(tokens)
    assert token_path().exists()
    assert not list(token_path().parent.glob(".device_bootstrap_token.json.*.tmp"))


def test_pair_complete_does_not_accept_local_bootstrap_fields(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    r = client.post(
        "/api/devices/pair/complete",
        json={**_BODY, "local_bootstrap": True, "setup_token": "old-admin-token"},
    )
    assert r.status_code == 422


def test_pairing_without_code_and_without_bootstrap_fails(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, client=("127.0.0.1", 50000))
    r = client.post(
        "/api/devices/pair/complete",
        json={"hostname": "kid-pc", "platform": "windows", "agent_version": "0.1.0-alpha.1"},
    )
    assert r.status_code == 400
