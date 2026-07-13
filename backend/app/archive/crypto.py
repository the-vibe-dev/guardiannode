"""Key slots and streaming authenticated encryption for GNA v1."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import struct
from pathlib import Path
from typing import Any, BinaryIO

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"GNARCHIVE1\n"
CHUNK_SIZE = 4 * 1024 * 1024
MAX_HEADER_BYTES = 1024 * 1024
ARGON2: dict[str, str | int] = {
    "name": "argon2id", "memory_kib": 65536, "iterations": 3, "parallelism": 1,
}
_KEY_AAD = b"guardiannode-archive-key-v1"


class CryptoError(ValueError):
    pass


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _wrap(key: bytes, wrapping_key: bytes, slot_type: str, extra: dict[str, Any]) -> dict[str, Any]:
    nonce = secrets.token_bytes(12)
    aad = _KEY_AAD + b":" + slot_type.encode("ascii")
    return {
        "type": slot_type,
        **extra,
        "nonce": b64(nonce),
        "wrapped_key": b64(AESGCM(wrapping_key).encrypt(nonce, key, aad)),
    }


def passphrase_slot(archive_key: bytes, passphrase: str) -> dict[str, Any]:
    if len(passphrase) < 12:
        raise CryptoError("archive passphrase must be at least 12 characters")
    salt = secrets.token_bytes(16)
    wrapping_key = hash_secret_raw(
        passphrase.encode(), salt,
        time_cost=int(ARGON2["iterations"]), memory_cost=int(ARGON2["memory_kib"]),
        parallelism=int(ARGON2["parallelism"]), hash_len=32, type=Type.ID,
    )
    return _wrap(archive_key, wrapping_key, "passphrase", {"kdf": ARGON2, "salt": b64(salt)})


def recipient_slot(archive_key: bytes, public_key: X25519PublicKey) -> dict[str, Any]:
    ephemeral = X25519PrivateKey.generate()
    salt = secrets.token_bytes(16)
    public_raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    shared = ephemeral.exchange(public_key)
    wrapping_key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=salt, info=_KEY_AAD + b":x25519"
    ).derive(shared)
    ephemeral_raw = ephemeral.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return _wrap(archive_key, wrapping_key, "x25519", {
        "kdf": "HKDF-SHA256", "salt": b64(salt), "ephemeral_public_key": b64(ephemeral_raw),
        "recipient_fingerprint": hashlib.sha256(public_raw).hexdigest(),
    })


def instance_slot(archive_key: bytes, master_key: bytes) -> dict[str, Any]:
    return _wrap(archive_key, master_key, "instance-master-key", {})


def unwrap_slot(
    slot: dict[str, Any], *, passphrase: str | None = None,
    private_key: X25519PrivateKey | None = None, master_key: bytes | None = None,
) -> bytes:
    slot_type = slot.get("type")
    try:
        if slot_type == "passphrase" and passphrase is not None:
            kdf = slot["kdf"]
            if kdf.get("name") != "argon2id":
                raise CryptoError("unsupported passphrase KDF")
            wrapping_key = hash_secret_raw(
                passphrase.encode(), unb64(slot["salt"]), time_cost=int(kdf["iterations"]),
                memory_cost=int(kdf["memory_kib"]), parallelism=int(kdf["parallelism"]),
                hash_len=32, type=Type.ID,
            )
        elif slot_type == "x25519" and private_key is not None:
            peer = X25519PublicKey.from_public_bytes(unb64(slot["ephemeral_public_key"]))
            wrapping_key = HKDF(
                algorithm=hashes.SHA256(), length=32, salt=unb64(slot["salt"]),
                info=_KEY_AAD + b":x25519",
            ).derive(private_key.exchange(peer))
        elif slot_type == "instance-master-key" and master_key is not None:
            wrapping_key = master_key
        else:
            raise CryptoError(f"no credential supplied for {slot_type!r} key slot")
        aad = _KEY_AAD + b":" + str(slot_type).encode("ascii")
        return AESGCM(wrapping_key).decrypt(
            unb64(slot["nonce"]), unb64(slot["wrapped_key"]), aad
        )
    except InvalidTag as exc:
        raise CryptoError("incorrect credential or altered archive key slot") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise CryptoError(f"invalid archive key slot: {exc}") from exc


def encrypt_file(source: Path, destination: Path, header: dict[str, Any], key: bytes) -> None:
    header_bytes = canonical_json(header)
    if len(header_bytes) > MAX_HEADER_BYTES:
        raise CryptoError("archive header is too large")
    temporary = destination.with_suffix(destination.suffix + ".partial")
    aes = AESGCM(key)
    try:
        with source.open("rb") as inp, temporary.open("wb") as out:
            out.write(MAGIC)
            out.write(struct.pack(">I", len(header_bytes)))
            out.write(header_bytes)
            index = 0
            while chunk := inp.read(CHUNK_SIZE):
                nonce = secrets.token_bytes(12)
                aad = header_bytes + index.to_bytes(8, "big")
                frame = nonce + aes.encrypt(nonce, chunk, aad)
                out.write(struct.pack(">I", len(frame)))
                out.write(frame)
                index += 1
            out.write(struct.pack(">I", 0))
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_header(stream: BinaryIO) -> tuple[dict[str, Any], bytes]:
    if stream.read(len(MAGIC)) != MAGIC:
        raise CryptoError("not a GuardianNode Archive v1")
    raw_length = stream.read(4)
    if len(raw_length) != 4:
        raise CryptoError("truncated archive header")
    length = struct.unpack(">I", raw_length)[0]
    if not 0 < length <= MAX_HEADER_BYTES:
        raise CryptoError("invalid archive header length")
    encoded = stream.read(length)
    if len(encoded) != length:
        raise CryptoError("truncated archive header")
    try:
        header = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise CryptoError("invalid archive header JSON") from exc
    if canonical_json(header) != encoded:
        raise CryptoError("archive header is not canonical")
    return header, encoded


def decrypt_file(source: Path, destination: Path, key: bytes) -> dict[str, Any]:
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with source.open("rb") as inp, temporary.open("wb") as out:
            header, header_bytes = read_header(inp)
            aes = AESGCM(key)
            index = 0
            while True:
                raw_length = inp.read(4)
                if len(raw_length) != 4:
                    raise CryptoError("truncated archive frame")
                length = struct.unpack(">I", raw_length)[0]
                if length == 0:
                    if inp.read(1):
                        raise CryptoError("trailing data after archive terminator")
                    break
                if length < 28 or length > CHUNK_SIZE + 28:
                    raise CryptoError("invalid archive frame length")
                frame = inp.read(length)
                if len(frame) != length:
                    raise CryptoError("truncated archive frame")
                nonce, ciphertext = frame[:12], frame[12:]
                try:
                    out.write(aes.decrypt(
                        nonce, ciphertext, header_bytes + index.to_bytes(8, "big")
                    ))
                except InvalidTag as exc:
                    raise CryptoError("archive payload authentication failed") from exc
                index += 1
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, destination)
        return header
    finally:
        temporary.unlink(missing_ok=True)


def load_public_key(path: Path) -> X25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, X25519PublicKey):
        raise CryptoError("recipient key must be an X25519 public key")
    return key


def load_private_key(path: Path) -> X25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, X25519PrivateKey):
        raise CryptoError("recipient key must be an X25519 private key")
    return key


def generate_recipient_key(private_path: Path, public_path: Path) -> str:
    if private_path.exists() or public_path.exists():
        raise CryptoError("refusing to overwrite an existing recovery key")
    private = X25519PrivateKey.generate()
    private_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    if os.name != "nt":
        os.chmod(private_path, 0o600)
    public = private.public_key()
    public_path.write_bytes(public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ))
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()
