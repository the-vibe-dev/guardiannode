"""Browser session expiry and revocation controls."""
from __future__ import annotations

from fastapi.testclient import TestClient

PASSWORD = "correct horse battery"


def _client(monkeypatch, tmp_path, *, now: float = 1_800_000_000.0) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    settings_mod.settings.session_idle_timeout_seconds = 60
    settings_mod.settings.session_absolute_timeout_seconds = 300
    settings_mod.settings.recent_auth_timeout_seconds = 30

    from app.api import auth as auth_mod
    from app.api import deps as deps_mod
    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app
    from app.services.setup_token import ensure_setup_token

    monkeypatch.setattr(auth_mod.time, "time", lambda: now)
    monkeypatch.setattr(deps_mod.time, "time", lambda: now)

    Base.metadata.create_all(bind=get_engine())
    client = TestClient(create_app(), client=("127.0.0.1", 50000))
    token = ensure_setup_token()
    response = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Parent",
            "password": PASSWORD,
            "recovery_code": "one two three",
            "setup_token": token,
        },
    )
    assert response.status_code == 200
    return client


def _csrf(client: TestClient) -> str:
    return client.get("/api/auth/csrf").json()["csrf_token"]


def test_idle_session_timeout_clears_browser_session(monkeypatch, tmp_path):
    clock = {"now": 1_800_000_000.0}
    client = _client(monkeypatch, tmp_path, now=clock["now"])

    from app.api import auth as auth_mod
    from app.api import deps as deps_mod

    monkeypatch.setattr(auth_mod.time, "time", lambda: clock["now"])
    monkeypatch.setattr(deps_mod.time, "time", lambda: clock["now"])

    assert client.get("/api/auth/me").status_code == 200
    clock["now"] += 61
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Session expired"


def test_absolute_session_timeout_ignores_recent_activity(monkeypatch, tmp_path):
    clock = {"now": 1_800_001_000.0}
    client = _client(monkeypatch, tmp_path, now=clock["now"])

    from app.api import auth as auth_mod
    from app.api import deps as deps_mod

    monkeypatch.setattr(auth_mod.time, "time", lambda: clock["now"])
    monkeypatch.setattr(deps_mod.time, "time", lambda: clock["now"])

    for _ in range(3):
        clock["now"] += 50
        assert client.get("/api/auth/me").status_code == 200
    clock["now"] = 1_800_001_301.0
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Session expired"


def test_recent_auth_timeout_uses_configured_window(monkeypatch, tmp_path):
    clock = {"now": 1_800_002_000.0}
    client = _client(monkeypatch, tmp_path, now=clock["now"])

    from app.api import auth as auth_mod
    from app.api import deps as deps_mod

    monkeypatch.setattr(auth_mod.time, "time", lambda: clock["now"])
    monkeypatch.setattr(deps_mod.time, "time", lambda: clock["now"])

    csrf = _csrf(client)
    clock["now"] += 31
    response = client.post(
        "/api/storage/export",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "step_up_required"
    assert response.json()["detail"]["level"] == "standard"
    audit = client.get("/api/audit").json()
    assert any(row["action"] == "auth.step_up.denied" for row in audit)

    csrf = _csrf(client)
    response = client.post(
        "/api/auth/reauth",
        json={"password": PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    response = client.post(
        "/api/storage/export",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


def test_logout_all_requires_csrf(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.post("/api/auth/logout-all")
    assert response.status_code == 403
    assert "csrf" in response.json()["detail"].lower()


def test_logout_all_revokes_other_browser_sessions(monkeypatch, tmp_path):
    client_a = _client(monkeypatch, tmp_path)
    client_b = TestClient(client_a.app, client=("127.0.0.1", 50001))

    response = client_b.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    assert client_b.get("/api/auth/me").status_code == 200

    csrf = _csrf(client_a)
    response = client_a.post("/api/auth/logout-all", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert client_a.get("/api/auth/me").status_code == 401

    response = client_b.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Session revoked"


def test_recovery_reset_revokes_existing_browser_sessions(monkeypatch, tmp_path):
    client_a = _client(monkeypatch, tmp_path)
    client_b = TestClient(client_a.app, client=("127.0.0.1", 50001))
    recovery_client = TestClient(client_a.app, client=("127.0.0.1", 50002))

    assert client_b.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert client_b.get("/api/auth/me").status_code == 200

    response = recovery_client.post(
        "/api/auth/recovery-reset",
        json={
            "recovery_code": "one two three",
            "new_password": "new correct horse battery",
        },
    )
    assert response.status_code == 200
    assert client_b.get("/api/auth/me").status_code == 401
    assert client_a.get("/api/auth/me").status_code == 401


def test_password_change_revokes_all_sessions(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    csrf = _csrf(client)
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "replacement horse battery"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["sessions_revoked"] is True
    assert client.get("/api/auth/me").status_code == 401
    assert client.post(
        "/api/auth/login", json={"password": "replacement horse battery"}
    ).status_code == 200


def test_specific_lan_bind_is_reported_as_beyond_loopback(monkeypatch, tmp_path):
    from app import settings as settings_mod

    assert settings_mod.Settings(data_dir=tmp_path, bind_host="127.0.0.1").binds_beyond_loopback() is False
    assert settings_mod.Settings(data_dir=tmp_path, bind_host="::1").binds_beyond_loopback() is False
    assert settings_mod.Settings(data_dir=tmp_path, bind_host="localhost").binds_beyond_loopback() is False
    assert settings_mod.Settings(data_dir=tmp_path, bind_host="192.168.1.42").binds_beyond_loopback() is True
    assert settings_mod.Settings(data_dir=tmp_path, bind_host="guardian-server").binds_beyond_loopback() is True
