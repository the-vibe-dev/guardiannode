from __future__ import annotations

import json


def test_pending_failure_retries_then_dead_letters(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    from app.services import screenshot_async

    screenshot_async.settings = settings_mod.settings
    token = screenshot_async.store_pending(b"image-bytes", {"device_id": "dev1"})
    for _ in range(4):
        screenshot_async._record_failure(token, RuntimeError("temporary classifier outage"))
        meta = json.loads((tmp_path / "pending" / f"{token}.json").read_text("utf-8"))
        assert meta["attempts"] >= 1
        assert "next_attempt_at" in meta
        assert (tmp_path / "pending" / f"{token}.enc").exists()

    screenshot_async._record_failure(token, RuntimeError("still down"))
    assert not (tmp_path / "pending" / f"{token}.json").exists()
    assert not (tmp_path / "pending" / f"{token}.enc").exists()
    assert (tmp_path / "pending_dead_letter" / f"{token}.json").exists()
    assert (tmp_path / "pending_dead_letter" / f"{token}.enc").exists()
