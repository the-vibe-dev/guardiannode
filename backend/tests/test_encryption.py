"""Tests for the AES-GCM encryption service."""
from __future__ import annotations

import os

import pytest

from app.services import encryption


def test_encrypt_decrypt_text_roundtrip():
    pt = "Hello GuardianNode"
    blob = encryption.encrypt_text(pt)
    assert blob != pt.encode("utf-8")
    assert encryption.decrypt_text(blob) == pt


def test_encrypt_decrypt_bytes_roundtrip():
    pt = b"\x00\x01\x02\xff" * 100
    blob = encryption.encrypt_bytes(pt)
    assert encryption.decrypt_bytes(blob) == pt


def test_aad_mismatch_fails():
    blob = encryption.encrypt_text("hello", aad=b"event:1")
    with pytest.raises(encryption.EncryptionError):
        encryption.decrypt_text(blob, aad=b"event:2")


def test_tampered_blob_fails():
    blob = bytearray(encryption.encrypt_text("hello"))
    # Flip a byte in the ciphertext portion
    blob[-5] ^= 0x01
    with pytest.raises(encryption.EncryptionError):
        encryption.decrypt_text(bytes(blob))


def test_key_persists_across_calls(tmp_path, monkeypatch):
    pt = "stay stable"
    blob = encryption.encrypt_text(pt)
    # Reset cache; key should reload from disk and decrypt correctly
    encryption._reset_cache()
    assert encryption.decrypt_text(blob) == pt


def test_master_key_status_records_raw_key_metadata():
    encryption.get_master_key()

    status = encryption.master_key_status()

    assert status["key_version"] == encryption.current_key_version()
    expected_storage = "dpapi-local-machine" if os.name == "nt" else "raw-file"
    assert status["storage"] == expected_storage
    assert status["raw_key_present"] is (os.name != "nt")
    assert status["dpapi_key_present"] is (os.name == "nt")
    assert status["metadata_present"] is True
    assert status["metadata"]["wrapping"] == expected_storage
    assert status["metadata"]["algorithm"] == "AES-256-GCM"


def test_existing_raw_key_loads_and_gets_metadata():
    key_path = encryption._key_path()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(b"k" * 32)
    encryption._reset_cache()

    assert encryption.get_master_key() == b"k" * 32

    status = encryption.master_key_status()
    expected_storage = "dpapi-local-machine" if os.name == "nt" else "raw-file"
    assert status["storage"] == expected_storage
    assert status["metadata"]["wrapping"] == expected_storage


def test_master_key_backup_export_import_roundtrip(tmp_path):
    original = encryption.get_master_key()
    backup = tmp_path / "master-key-backup.json"

    assert encryption.export_master_key_backup(backup, "correct horse battery staple") == backup
    assert b"master.key" not in backup.read_bytes()

    for path in (encryption._key_path(), encryption._dpapi_key_path()):
        if path.exists():
            path.unlink()
    encryption._metadata_path().unlink()
    encryption._reset_cache()
    encryption.import_master_key_backup(backup, "correct horse battery staple")

    assert encryption.get_master_key() == original
    assert encryption.master_key_status()["metadata"]["migrated_from"] == "portable-backup"


def test_master_key_backup_refuses_overwrite(tmp_path):
    backup = tmp_path / "master-key-backup.json"
    encryption.export_master_key_backup(backup, "correct horse battery staple")

    with pytest.raises(encryption.EncryptionError):
        encryption.export_master_key_backup(backup, "correct horse battery staple")

    with pytest.raises(encryption.EncryptionError):
        encryption.import_master_key_backup(backup, "correct horse battery staple")


def test_master_key_backup_rejects_wrong_passphrase(tmp_path):
    backup = tmp_path / "master-key-backup.json"
    encryption.export_master_key_backup(backup, "correct horse battery staple")
    for path in (encryption._key_path(), encryption._dpapi_key_path()):
        if path.exists():
            path.unlink()
    encryption._metadata_path().unlink()
    encryption._reset_cache()

    with pytest.raises(encryption.EncryptionError):
        encryption.import_master_key_backup(backup, "wrong horse battery")
