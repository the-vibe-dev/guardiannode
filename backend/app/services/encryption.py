"""AES-GCM encryption for sensitive event fields and evidence blobs.

The master key is generated on first run. On Windows, new keys are wrapped with
DPAPI LocalMachine before being written to disk. On Linux and other platforms,
the current alpha stores the raw key with restrictive filesystem permissions.
Anyone who can read a raw key file can decrypt the evidence store; see
docs/THREAT_MODEL.md for the honest boundary.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import json
import os
import secrets
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.settings import settings

_MASTER_KEY_FILE = "master.key"
_MASTER_KEY_DPAPI_FILE = "master.key.dpapi"
_MASTER_KEY_METADATA_FILE = "master.key.json"
_KEY_VERSION = 1
_NONCE_SIZE = 12  # AES-GCM standard
_STREAM_MAGIC = b"GNSTREAM1\n"
_STREAM_CHUNK_SIZE = 4 * 1024 * 1024
_DPAPI_DESCRIPTION = "GuardianNode backend master key"
_DPAPI_ENTROPY = b"GuardianNode backend master key v1"
_CRYPTPROTECT_LOCAL_MACHINE = 0x4
_KEY_BACKUP_FORMAT = "guardiannode-master-key-backup-v1"
_KEY_BACKUP_KDF = {"name": "scrypt", "n": 2**14, "r": 8, "p": 1, "length": 32}
_KEY_BACKUP_MIN_PASSPHRASE = 12


class EncryptionError(Exception):
    pass


def _key_path() -> Path:
    return settings.keys_dir / _MASTER_KEY_FILE


def _dpapi_key_path() -> Path:
    return settings.keys_dir / _MASTER_KEY_DPAPI_FILE


def _metadata_path() -> Path:
    return settings.keys_dir / _MASTER_KEY_METADATA_FILE


def _write_restricted(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    if os.name != "nt":
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    tmp.replace(path)


def _load_raw_key(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) != 32:
        raise EncryptionError("Master key file is corrupt (wrong size)")
    return data


def _write_key_metadata(*, wrapping: str, migrated_from: str | None = None) -> None:
    payload: dict[str, Any] = {
        "key_version": _KEY_VERSION,
        "algorithm": "AES-256-GCM",
        "wrapping": wrapping,
        "created_or_migrated_at": datetime.now(UTC).isoformat(),
    }
    if migrated_from:
        payload["migrated_from"] = migrated_from
    _write_restricted(
        _metadata_path(),
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_ubyte]]:
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return _DataBlob(len(data), buffer), buffer


def _bytes_from_blob(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise EncryptionError("DPAPI is only available on Windows")
    from ctypes import wintypes

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    in_blob, _in_buffer = _blob_from_bytes(data)
    entropy_blob, _entropy_buffer = _blob_from_bytes(_DPAPI_ENTROPY)
    out_blob = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        _DPAPI_DESCRIPTION,
        ctypes.byref(entropy_blob),
        None,
        None,
        _CRYPTPROTECT_LOCAL_MACHINE,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise EncryptionError(f"DPAPI CryptProtectData failed: {ctypes.get_last_error()}")
    try:
        return _bytes_from_blob(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise EncryptionError("DPAPI is only available on Windows")
    from ctypes import wintypes

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    in_blob, _in_buffer = _blob_from_bytes(data)
    entropy_blob, _entropy_buffer = _blob_from_bytes(_DPAPI_ENTROPY)
    out_blob = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise EncryptionError(f"DPAPI CryptUnprotectData failed: {ctypes.get_last_error()}")
    try:
        plaintext = _bytes_from_blob(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    if len(plaintext) != 32:
        raise EncryptionError("DPAPI master key payload is corrupt (wrong size)")
    return plaintext


def _write_dpapi_key(key: bytes, *, migrated_from: str | None = None) -> None:
    _write_restricted(_dpapi_key_path(), _dpapi_protect(key))
    _write_key_metadata(wrapping="dpapi-local-machine", migrated_from=migrated_from)


def _store_master_key(key: bytes, *, migrated_from: str | None = None) -> None:
    if len(key) != 32:
        raise EncryptionError("Master key must be 32 bytes")
    if os.name == "nt":
        _write_dpapi_key(key, migrated_from=migrated_from)
    else:
        _write_restricted(_key_path(), key)
        _write_key_metadata(wrapping="raw-file", migrated_from=migrated_from)


def _load_or_generate_master_key() -> bytes:
    settings.ensure_dirs()
    raw_path = _key_path()
    dpapi_path = _dpapi_key_path()
    if os.name == "nt" and dpapi_path.exists():
        key = _dpapi_unprotect(dpapi_path.read_bytes())
        if not _metadata_path().exists():
            _write_key_metadata(wrapping="dpapi-local-machine")
        return key
    if raw_path.exists():
        key = _load_raw_key(raw_path)
        if os.name == "nt":
            # Preserve compatibility with existing alpha installs. The raw key
            # remains in place until an administrator removes it after backup.
            _write_dpapi_key(key, migrated_from="raw-file")
        elif not _metadata_path().exists():
            _write_key_metadata(wrapping="raw-file")
        return key

    key = secrets.token_bytes(32)
    _store_master_key(key)
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


def _chunk_aad(aad: bytes | None, index: int) -> bytes:
    prefix = aad or b""
    return prefix + b":chunk:" + index.to_bytes(8, "big")


def encrypt_file_to_disk(
    src: Path,
    dest: Path,
    *,
    aad: bytes | None = None,
    chunk_size: int = _STREAM_CHUNK_SIZE,
) -> None:
    """Encrypt a file without loading it all into memory.

    Output format:
        magic || repeated(uint32_be length || nonce || ciphertext+tag) || 0 length
    """
    if chunk_size <= 0:
        raise EncryptionError("chunk_size must be positive")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    aes = AESGCM(get_master_key())
    index = 0
    with src.open("rb") as inp, tmp.open("wb") as out:
        out.write(_STREAM_MAGIC)
        while True:
            plaintext = inp.read(chunk_size)
            if not plaintext:
                break
            nonce = secrets.token_bytes(_NONCE_SIZE)
            encrypted = nonce + aes.encrypt(nonce, plaintext, _chunk_aad(aad, index))
            out.write(struct.pack(">I", len(encrypted)))
            out.write(encrypted)
            index += 1
        out.write(struct.pack(">I", 0))
    tmp.replace(dest)


def decrypt_stream_file_from_disk(src: Path, *, aad: bytes | None = None) -> bytes:
    """Decrypt a chunked stream file into memory.

    This is intended for tests and admin tooling. Runtime exports use
    ``encrypt_file_to_disk`` so the hot path stays bounded by chunk size.
    """
    aes = AESGCM(get_master_key())
    out = bytearray()
    with src.open("rb") as inp:
        if inp.read(len(_STREAM_MAGIC)) != _STREAM_MAGIC:
            raise EncryptionError("not a GuardianNode stream ciphertext")
        index = 0
        while True:
            raw_len = inp.read(4)
            if len(raw_len) != 4:
                raise EncryptionError("stream ciphertext truncated")
            frame_len = struct.unpack(">I", raw_len)[0]
            if frame_len == 0:
                break
            if frame_len < _NONCE_SIZE + 16:
                raise EncryptionError("stream frame too short")
            frame = inp.read(frame_len)
            if len(frame) != frame_len:
                raise EncryptionError("stream frame truncated")
            nonce, ct = frame[:_NONCE_SIZE], frame[_NONCE_SIZE:]
            try:
                out.extend(aes.decrypt(nonce, ct, _chunk_aad(aad, index)))
            except Exception as e:
                raise EncryptionError(f"stream decryption failed: {e}") from e
            index += 1
    return bytes(out)


def current_key_version() -> int:
    return _KEY_VERSION


def master_key_status() -> dict[str, Any]:
    """Return non-secret key storage status for diagnostics and backup checks."""
    raw_present = _key_path().exists()
    dpapi_present = _dpapi_key_path().exists()
    metadata: dict[str, Any] = {}
    metadata_present = _metadata_path().exists()
    if metadata_present:
        try:
            metadata = json.loads(_metadata_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {"unreadable": True}

    if dpapi_present:
        storage = "dpapi-local-machine"
    elif raw_present:
        storage = "raw-file"
    else:
        storage = "missing"

    return {
        "key_version": _KEY_VERSION,
        "storage": storage,
        "raw_key_present": raw_present,
        "dpapi_key_present": dpapi_present,
        "metadata_present": metadata_present,
        "metadata": metadata,
    }


def _derive_backup_key(passphrase: str, salt: bytes, *, kdf: dict[str, Any] | None = None) -> bytes:
    if len(passphrase) < _KEY_BACKUP_MIN_PASSPHRASE:
        raise EncryptionError("Backup passphrase must be at least 12 characters")
    params = kdf or _KEY_BACKUP_KDF
    if params.get("name") != "scrypt":
        raise EncryptionError("Unsupported key-backup KDF")
    return Scrypt(
        salt=salt,
        length=int(params["length"]),
        n=int(params["n"]),
        r=int(params["r"]),
        p=int(params["p"]),
    ).derive(passphrase.encode("utf-8"))


def export_master_key_backup(destination: Path, passphrase: str, *, overwrite: bool = False) -> Path:
    """Write a portable, passphrase-encrypted backup of the current master key."""
    destination = destination.expanduser()
    if destination.exists() and not overwrite:
        raise EncryptionError(f"Backup already exists: {destination}")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    backup_key = _derive_backup_key(passphrase, salt)
    ciphertext = AESGCM(backup_key).encrypt(nonce, get_master_key(), _KEY_BACKUP_FORMAT.encode("ascii"))
    payload = {
        "format": _KEY_BACKUP_FORMAT,
        "created_at": datetime.now(UTC).isoformat(),
        "key_version": _KEY_VERSION,
        "kdf": _KEY_BACKUP_KDF,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    _write_restricted(
        destination,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return destination


def import_master_key_backup(source: Path, passphrase: str, *, overwrite: bool = False) -> None:
    """Restore the master key from a portable backup file.

    Existing key material is not overwritten unless ``overwrite`` is true.
    """
    global _master_key_cache
    if not overwrite and (_key_path().exists() or _dpapi_key_path().exists()):
        raise EncryptionError("Refusing to overwrite existing master key")
    try:
        payload = json.loads(source.expanduser().read_text(encoding="utf-8"))
        if payload.get("format") != _KEY_BACKUP_FORMAT:
            raise EncryptionError("Unsupported master-key backup format")
        salt = base64.b64decode(payload["salt"])
        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ciphertext"])
        backup_key = _derive_backup_key(passphrase, salt, kdf=payload["kdf"])
        key = AESGCM(backup_key).decrypt(nonce, ciphertext, _KEY_BACKUP_FORMAT.encode("ascii"))
    except InvalidTag as e:
        raise EncryptionError("Backup passphrase is incorrect or backup is corrupt") from e
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        raise EncryptionError(f"Invalid master-key backup: {e}") from e
    if len(key) != 32:
        raise EncryptionError("Master-key backup payload has wrong size")
    _store_master_key(key, migrated_from="portable-backup")
    _master_key_cache = key


def _prompt_passphrase(*, confirm: bool = False) -> str:
    first = getpass.getpass("Master-key backup passphrase: ")
    if confirm:
        second = getpass.getpass("Confirm passphrase: ")
        if first != second:
            raise EncryptionError("Passphrases do not match")
    return first


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GuardianNode encryption key utility")
    subcommands = parser.add_subparsers(dest="command", required=True)

    export_cmd = subcommands.add_parser(
        "export-key-backup",
        help="Create a portable passphrase-encrypted master-key backup",
    )
    export_cmd.add_argument("destination", type=Path)
    export_cmd.add_argument("--overwrite", action="store_true")

    import_cmd = subcommands.add_parser(
        "import-key-backup",
        help="Restore a portable passphrase-encrypted master-key backup",
    )
    import_cmd.add_argument("source", type=Path)
    import_cmd.add_argument("--overwrite", action="store_true")

    status_cmd = subcommands.add_parser("key-status", help="Print non-secret key storage status")
    status_cmd.set_defaults(status=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "export-key-backup":
            path = export_master_key_backup(
                args.destination,
                _prompt_passphrase(confirm=True),
                overwrite=args.overwrite,
            )
            print(path)
            return 0
        if args.command == "import-key-backup":
            import_master_key_backup(
                args.source,
                _prompt_passphrase(),
                overwrite=args.overwrite,
            )
            print("master key restored")
            return 0
        if args.command == "key-status":
            print(json.dumps(master_key_status(), indent=2, sort_keys=True))
            return 0
    except EncryptionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli())
