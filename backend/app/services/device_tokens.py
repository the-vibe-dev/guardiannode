"""Device token format and constant-time keyed verification.

Tokens issued at pairing look like::

    gn_dev_<device_id>_<random_secret>

Device tokens are random machine credentials, not human passwords. They are
therefore stored as HMAC-SHA256 digests under a separate server-only pepper,
which keeps every request cheap and bounded while protecting a copied database.

GuardianNode's family-beta migration intentionally invalidates every legacy
Argon2 token. Devices must be paired again after the upgrade.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.db.models import Device

TOKEN_PREFIX = "gn_dev_"
TOKEN_DIGEST_PREFIX = "hmac-sha256:"
_pepper_lock = threading.Lock()
_pepper_cache: tuple[Path, bytes] | None = None


def _write_new_pepper(path: Path, pepper: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(pepper)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _pepper() -> bytes:
    global _pepper_cache
    path = settings_mod.settings.device_token_pepper_path
    cached = _pepper_cache
    if cached is not None and cached[0] == path:
        return cached[1]
    with _pepper_lock:
        cached = _pepper_cache
        if cached is not None and cached[0] == path:
            return cached[1]
        _write_new_pepper(path, secrets.token_bytes(32))
        value = path.read_bytes()
        if len(value) != 32:
            raise RuntimeError("device-token pepper is corrupt")
        _pepper_cache = (path, value)
        return value


def _digest(secret: str) -> str:
    digest = hmac.new(_pepper(), secret.encode("utf-8"), hashlib.sha256).hexdigest()
    return TOKEN_DIGEST_PREFIX + digest


def issue_token(device_id: str) -> tuple[str, str]:
    """Create a new device token and its keyed digest for storage."""
    secret = secrets.token_urlsafe(32)
    return f"{TOKEN_PREFIX}{device_id}_{secret}", _digest(secret)


def parse_token(token: str) -> tuple[str, str] | None:
    """Split a structured token into (device_id, secret); None if legacy/opaque."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    rest = token[len(TOKEN_PREFIX):]
    # device ids are ULIDs (no underscores); the secret may contain them.
    device_id, sep, secret = rest.partition("_")
    if not sep or not device_id or not secret:
        return None
    return device_id, secret


def authenticate(db: Session, token: str) -> Device | None:
    """Resolve a current-format bearer token to a paired device, or ``None``."""
    parsed = parse_token(token)
    if parsed is None:
        return None
    device_id, secret = parsed
    device = db.get(Device, device_id)
    if (
        device is not None
        and device.paired
        and device.token_hash
        and device.token_hash.startswith(TOKEN_DIGEST_PREFIX)
        and hmac.compare_digest(_digest(secret), device.token_hash)
    ):
        return device
    return None


def _reset_cache() -> None:
    """Reset the test-only in-process pepper cache."""
    global _pepper_cache
    _pepper_cache = None
