from __future__ import annotations

from pathlib import Path

from src import tray_app


def test_tray_auth_does_not_use_recovery_codes() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8").lower()
    assert "verify_recovery_code" not in source
    assert "12-word recovery code" not in source
    assert "httpx" not in source
    assert "/api/auth/login" not in source


def test_tray_pause_sends_password_to_broker(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    class FakeBrokerClient:
        def status(self) -> dict:
            return {"device_id": "dev-1"}

        def pause(self, duration_seconds: int, *, actor: str, parent_password: str) -> dict:
            calls.append((duration_seconds, parent_password))
            return {"paused": True}

    monkeypatch.setattr(tray_app, "BrokerClient", FakeBrokerClient)
    monkeypatch.setattr(tray_app, "_ask_password", lambda: "correct horse")
    monkeypatch.setattr(tray_app, "_ask_duration", lambda: 900)

    tray_app.pause_flow()

    assert calls == [(900, "correct horse")]


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
