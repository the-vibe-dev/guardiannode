from __future__ import annotations

import json


def _reload_screenshot_async(monkeypatch, tmp_path):
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    from app.services import encryption, screenshot_async

    encryption._reset_cache()
    screenshot_async.settings = settings_mod.settings
    return screenshot_async


def test_store_pending_atomic_final_files(monkeypatch, tmp_path):
    screenshot_async = _reload_screenshot_async(monkeypatch, tmp_path)
    from app.services import encryption

    token = screenshot_async.store_pending(b"image-bytes", {"device_id": "dev1"})
    pending = tmp_path / "pending"
    meta = json.loads((pending / f"{token}.json").read_text("utf-8"))

    assert meta["token"] == token
    assert meta["storage_state"] == "ready"
    assert encryption.decrypt_blob_from_disk(
        pending / f"{token}.enc", aad=token.encode("ascii")
    ) == b"image-bytes"
    assert not list(pending.glob("*.tmp"))
    assert not list(pending.glob(".*.tmp"))


def test_ready_tokens_dead_letters_incomplete_pending_pairs(monkeypatch, tmp_path):
    screenshot_async = _reload_screenshot_async(monkeypatch, tmp_path)
    pending = tmp_path / "pending"
    pending.mkdir()
    (pending / "enc-only.enc").write_bytes(b"ciphertext")
    (pending / "json-only.json").write_text(json.dumps({"token": "json-only"}), encoding="utf-8")
    (pending / "bad.enc").write_bytes(b"ciphertext")
    (pending / "bad.json").write_text("{not json", encoding="utf-8")
    (pending / ".abandoned.enc.01.tmp").write_bytes(b"partial")

    assert screenshot_async._ready_tokens() == []

    dead = tmp_path / "pending_dead_letter"
    assert (dead / "enc-only.enc").exists()
    assert json.loads((dead / "enc-only.json").read_text("utf-8"))["dead_letter_reason"] == (
        "missing pending metadata"
    )
    assert (dead / "json-only.json").exists()
    assert json.loads((dead / "json-only.json").read_text("utf-8"))["dead_letter_reason"] == (
        "missing pending ciphertext"
    )
    assert (dead / "bad.enc").exists()
    assert json.loads((dead / "bad.json").read_text("utf-8"))["dead_letter_reason"] == (
        "invalid pending metadata"
    )
    assert (dead / ".abandoned.enc.01.tmp").exists()


def test_pending_failure_retries_then_dead_letters(monkeypatch, tmp_path):
    screenshot_async = _reload_screenshot_async(monkeypatch, tmp_path)
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
