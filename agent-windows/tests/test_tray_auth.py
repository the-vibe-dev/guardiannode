from __future__ import annotations

from pathlib import Path

from src import tray_app


def test_tray_auth_does_not_use_recovery_codes() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8").lower()
    assert "verify_recovery_code" not in source
    assert "12-word recovery code" not in source


def test_tray_refuses_remote_password_over_plain_http(monkeypatch) -> None:
    def _unexpected_client(*_args, **_kwargs):
        raise AssertionError("remote password check should not be attempted")

    monkeypatch.setattr(tray_app, "verify_password", lambda _password: False)
    monkeypatch.setattr(tray_app, "_backend_url", lambda: "http://192.0.2.10:8787")
    monkeypatch.setattr(tray_app.httpx, "Client", _unexpected_client)

    assert not tray_app._verify_parent_password("correct horse battery staple")
