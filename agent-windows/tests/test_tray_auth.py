from __future__ import annotations

from pathlib import Path

from src import tray_app


def test_tray_auth_does_not_use_recovery_codes() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8").lower()
    assert "verify_recovery_code" not in source
    assert "12-word recovery code" not in source
    assert "httpx" not in source
    assert "/api/auth/login" not in source


def test_tray_pause_opens_parent_dashboard(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tray_app, "_open_dashboard", lambda: calls.append("dashboard"))

    tray_app.pause_flow()

    assert calls == ["dashboard"]


def test_tray_never_handles_parent_secrets_or_prompt_temp_files() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8").lower()
    assert "parent_password" not in source
    assert ".gnprompt" not in source
    assert "ask_password" not in source


def test_tray_reads_backend_and_device_from_broker_before_legacy_files(monkeypatch) -> None:
    class FakeBrokerClient:
        def status(self) -> dict:
            return {
                "backend_url": "http://127.0.0.1:8787",
                "device_id": "dev-from-broker",
            }

    monkeypatch.setattr(tray_app, "BrokerClient", FakeBrokerClient)
    monkeypatch.setattr(tray_app, "load_credentials", lambda: {"device_id": "legacy-dev"})

    assert tray_app._backend_url() == "http://127.0.0.1:8787"
    assert tray_app._device_id() == "dev-from-broker"
