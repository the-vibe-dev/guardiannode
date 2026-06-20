"""AES-GCM encryption for sensitive event fields and evidence blobs.

The master key is generated on first run and stored as a raw key file at
`settings.keys_dir / "master.key"`. It is protected by filesystem permissions
only: 0600 on POSIX, and a SYSTEM/Administrators-only ACL applied by the
Windows installer. DPAPI wrapping is NOT currently implemented — anyone who
can read the key file can decrypt the evidence store. See docs/THREAT_MODEL.md.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.settings import settings

_MASTER_KEY_FILE = "master.key"
_KEY_VERSION = 1
_NONCE_SIZE = 12  # AES-GCM standard


class EncryptionError(Exception):
    pass


def _key_path() -> Path:
    return settings.keys_dir / _MASTER_KEY_FILE


def _load_or_generate_master_key() -> bytes:
    settings.ensure_dirs()
    path = _key_path()
    if path.exists():
        data = path.read_bytes()
        if len(data) != 32:
            raise EncryptionError("Master key file is corrupt (wrong size)")
        return data
    # Generate
    key = secrets.token_bytes(32)
    # Atomic write with restricted perms
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(key)
    if os.name != "nt":
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    tmp.replace(path)
    return key


_master_key_cache: bytes | None = None


def get_master_key() -> bytes:
    global _master_key_cache
    if _master_key_cache is None:
        _master_key_cache = _load_or_generate_master_key()
    return _master_key_cache


def _reset_cache() -> None:
    """For tests only."""
    global _master_key_cache
    _master_key_cache = None


def encrypt_bytes(plaintext: bytes, *, aad: bytes | None = None) -> bytes:
    """Encrypt bytes. Output format: nonce (12) || ciphertext+tag."""
    if plaintext is None:
        raise EncryptionError("plaintext is None")
    key = get_master_key()
    aes = AESGCM(key)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ct = aes.encrypt(nonce, plaintext, aad)
    return nonce + ct


def decrypt_bytes(blob: bytes, *, aad: bytes | None = None) -> bytes:
    """Inverse of encrypt_bytes."""
    if not blob or len(blob) < _NONCE_SIZE + 16:
        raise EncryptionError("ciphertext too short")
    nonce, ct = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
    key = get_master_key()
    aes = AESGCM(key)
    try:
        return aes.decrypt(nonce, ct, aad)
    except Exception as e:
        raise EncryptionError(f"decryption failed: {e}") from e


def encrypt_text(plaintext: str, *, aad: bytes | None = None) -> bytes:
    return encrypt_bytes(plaintext.encode("utf-8"), aad=aad)


def decrypt_text(blob: bytes, *, aad: bytes | None = None) -> str:
    return decrypt_bytes(blob, aad=aad).decode("utf-8")


def encrypt_blob_to_disk(plaintext: bytes, dest: Path, *, aad: bytes | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    enc = encrypt_bytes(plaintext, aad=aad)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(enc)
    tmp.replace(dest)


def decrypt_blob_from_disk(src: Path, *, aad: bytes | None = None) -> bytes:
    return decrypt_bytes(src.read_bytes(), aad=aad)


def current_key_version() -> int:
    return _KEY_VERSION
