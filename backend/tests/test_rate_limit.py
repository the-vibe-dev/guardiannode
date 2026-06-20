"""Brute-force protection on login, recovery reset, and pairing."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services import rate_limit


@pytest.fixture(autouse=True)
def clear_rate_limits():
    rate_limit._clear_all()
    yield
    rate_limit._clear_all()


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    from app.main import create_app
    from app.db.models import Base
    from app.db.session import get_engine

    Base.metadata.create_all(bind=get_engine())
    client = TestClient(create_app())
    r = client.post(
        "/api/auth/setup",
        json={"display_name": "Parent", "password": "correct horse battery", "recovery_code": "one two three"},
    )
    assert r.status_code == 200
    client.post("/api/auth/logout")
    return client


def test_login_locks_out_after_repeated_failures(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for _ in range(rate_limit.MAX_FAILURES):
        r = client.post("/api/auth/login", json={"password": "wrong-password"})
        assert r.status_code == 401
    r = client.post("/api/auth/login", json={"password": "wrong-password"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # Even the correct password is rejected while blocked.
    r = client.post("/api/auth/login", json={"password": "correct horse battery"})
    assert r.status_code == 429


def test_login_success_resets_counter(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for _ in range(rate_limit.MAX_FAILURES - 1):
        client.post("/api/auth/login", json={"password": "wrong-password"})
    r = client.post("/api/auth/login", json={"password": "correct horse battery"})
    assert r.status_code == 200
    # Counter reset: failures start from zero again.
    r = client.post("/api/auth/login", json={"password": "wrong-password"})
    assert r.status_code == 401


def test_recovery_reset_rate_limited(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for _ in range(rate_limit.MAX_FAILURES):
        r = client.post(
            "/api/auth/recovery-reset",
            json={"recovery_code": "bad code", "new_password": "another password 123"},
        )
        assert r.status_code == 401
    r = client.post(
        "/api/auth/recovery-reset",
        json={"recovery_code": "bad code", "new_password": "another password 123"},
    )
    assert r.status_code == 429


def test_pairing_rate_limited(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    body = {"code": "000000", "hostname": "kid-pc", "platform": "windows", "agent_version": "0.1.0-alpha.1"}
    for _ in range(rate_limit.MAX_FAILURES):
        r = client.post("/api/devices/pair/complete", json=body)
        assert r.status_code == 400
    r = client.post("/api/devices/pair/complete", json=body)
    assert r.status_code == 429
