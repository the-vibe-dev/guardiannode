"""Tests for the AES-GCM encryption service."""
from __future__ import annotations

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
