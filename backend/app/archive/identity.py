"""Stable instance identity used to sign archive manifests."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.services import encryption

_FORMAT = "guardiannode-instance-identity-v1"
_AAD = _FORMAT.encode("ascii")


@dataclass(frozen=True)
class InstanceIdentity:
    instance_id: str
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @property
    def public_bytes(self) -> bytes:
        return self.public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.public_bytes).hexdigest()


def identity_path(keys_dir: Path) -> Path:
    return keys_dir / "instance-identity.json"


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    temporary.write_bytes(data)
    if os.name != "nt":
        os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def load_or_create(keys_dir: Path) -> InstanceIdentity:
    path = identity_path(keys_dir)
    if path.exists():
        try:
            payload = json.loads(path.read_text("utf-8"))
            if payload.get("format") != _FORMAT:
                raise ValueError("unsupported identity format")
            private_raw = encryption.decrypt_bytes(
                base64.b64decode(payload["private_key_enc"]), aad=_AAD
            )
            private = Ed25519PrivateKey.from_private_bytes(private_raw)
            public = private.public_key()
            expected = base64.b64decode(payload["public_key"])
            if public.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ) != expected:
                raise ValueError("public key mismatch")
            return InstanceIdentity(str(payload["instance_id"]), private, public)
        except Exception as exc:
            raise RuntimeError(f"instance identity is corrupt: {exc}") from exc

    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = private.public_key()
    payload = {
        "format": _FORMAT,
        "instance_id": str(uuid4()),
        "algorithm": "Ed25519",
        "public_key": base64.b64encode(
            public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ).decode("ascii"),
        "private_key_enc": base64.b64encode(
            encryption.encrypt_bytes(private_raw, aad=_AAD)
        ).decode("ascii"),
    }
    _write_private(path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
    return InstanceIdentity(payload["instance_id"], private, public)
