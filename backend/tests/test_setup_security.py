"""First-run setup must require a local one-time setup token."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app

    Base.metadata.create_all(bind=get_engine())
    return create_app()


def _setup_body(token: str) -> dict:
    return {
        "display_name": "Parent",
        "password": "correct-horse-battery",
        "recovery_code": "alpha bravo gamma delta",
        "setup_token": token,
    }


def test_remote_first_admin_without_setup_token_rejected(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path), client=("192.168.1.50", 50000))
    r = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Mallory",
            "password": "correct-horse-battery",
            "recovery_code": "stolen phrase",
            "setup_token": "wrong",
        },
    )
    assert r.status_code == 401


def test_recovery_generation_requires_setup_token(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path), client=("192.168.1.50", 50000))
    r = client.post("/api/setup/recovery", json={"setup_token": "wrong"})
    assert r.status_code == 401


def test_setup_token_is_single_use(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path), client=("192.168.1.50", 50000))
    from app.services.setup_token import ensure_setup_token

    token = ensure_setup_token()
    assert client.post("/api/setup/recovery", json={"setup_token": token}).status_code == 200
    r = client.post("/api/auth/setup", json=_setup_body(token))
    assert r.status_code == 200, r.text

    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    r = client.post("/api/auth/setup", json=_setup_body(token), headers={"X-CSRF-Token": csrf})
    assert r.status_code in {400, 401}


def test_expired_setup_token_rejected(monkeypatch, tmp_path):
    client = TestClient(_app(monkeypatch, tmp_path))
    from app.services.setup_token import token_path

    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text(
        json.dumps({
            "token": "expired-token",
            "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        }),
        encoding="utf-8",
    )

    r = client.post("/api/auth/setup", json=_setup_body("expired-token"))
    assert r.status_code == 401


def test_concurrent_setup_creates_exactly_one_admin(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    from app.db.models import User
    from app.db.session import get_sessionmaker
    from app.services.setup_token import ensure_setup_token

    token = ensure_setup_token()

    def post_setup(name: str) -> int:
        with TestClient(app, client=("192.168.1.50", 50000)) as client:
            r = client.post("/api/auth/setup", json={**_setup_body(token), "display_name": name})
            return r.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(post_setup, ["Parent A", "Parent B"]))

    assert statuses == [200, 400] or statuses == [200, 401]
    s = get_sessionmaker()()
    try:
        assert s.query(User).filter(User.role == "admin").count() == 1
    finally:
        s.close()
