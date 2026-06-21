"""Smoke test for the FastAPI app."""
from __future__ import annotations

import pytest
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


def test_default_trusted_hosts_reject_unknown_host(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GUARDIANNODE_ALLOWED_HOSTS", raising=False)
    from app import settings as settings_mod
    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    from app.main import create_app

    client = TestClient(create_app())
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_configured_lan_hosts_are_trusted(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUARDIANNODE_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("GUARDIANNODE_ALLOWED_HOSTS", "192.168.1.42,guardian-server,127.0.0.1,localhost,fd00::42")
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    from app import main as main_api
    main_api.settings = settings_mod.settings

    app = main_api.create_app()
    assert TestClient(app, base_url="http://192.168.1.42:8787").get("/api/health").status_code == 200
    assert TestClient(app, base_url="http://guardian-server").get("/api/health").status_code == 200
    assert TestClient(app).get("/api/health", headers={"host": "[fd00::42]:8787"}).status_code == 200
    assert TestClient(app, base_url="http://192.168.1.43:8787").get("/api/health").status_code == 400


def test_wildcard_allowed_hosts_only_survives_in_dev_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUARDIANNODE_ALLOWED_HOSTS", "*")
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.dev_mode = False
    with pytest.raises(ValueError, match="only allowed"):
        settings_mod.settings.effective_allowed_hosts()

    settings_mod.settings.dev_mode = True
    assert settings_mod.settings.effective_allowed_hosts() == ["*"]


def test_runtime_settings_requires_parent_and_reports_effective_config(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUARDIANNODE_CLASSIFIER_TIER", "text_only")
    monkeypatch.setenv("GUARDIANNODE_TEXT_MODEL", "llama3.2:1b")
    monkeypatch.setenv("GUARDIANNODE_VISION_MODEL", "")
    monkeypatch.setenv("GUARDIANNODE_OLLAMA_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("GUARDIANNODE_TEXT_OLLAMA_URL", "http://127.0.0.1:11435")
    monkeypatch.setenv("GUARDIANNODE_CLASSIFIER_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("GUARDIANNODE_OLLAMA_STATUS_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("GUARDIANNODE_OLLAMA_PULL_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("GUARDIANNODE_ALLOWED_HOSTS", "127.0.0.1,localhost")
    from app import settings as settings_mod
    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    from app.api import health as health_api
    health_api.settings = settings_mod.settings
    from app import main as main_api
    from app.db.models import Base
    from app.db.session import get_engine
    main_api.settings = settings_mod.settings
    from app.services.setup_token import ensure_setup_token

    Base.metadata.create_all(bind=get_engine())
    client = TestClient(main_api.create_app(), base_url="http://127.0.0.1")
    r = client.get("/api/health/runtime-settings")
    assert r.status_code == 401

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

    r = client.get("/api/health/runtime-settings")
    assert r.status_code == 200
    body = r.json()
    assert body["classifier"]["tier"] == "text_only"
    assert body["classifier"]["text_model"] == "llama3.2:1b"
    assert body["classifier"]["classifier_timeout_seconds"] == 120
    assert body["ollama"]["text_url"] == "http://127.0.0.1:11435"
    assert body["ollama"]["status_timeout_seconds"] == 4
    assert body["ollama"]["pull_timeout_seconds"] == 900
    assert body["security"]["allowed_hosts"] == ["127.0.0.1", "localhost"]
    assert body["database"] == {"driver": "sqlite"}
    assert "session_secret" not in str(body).lower()
    assert "db_url" not in str(body).lower()
