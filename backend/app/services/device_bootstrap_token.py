"""Purpose-bound one-time token for local device bootstrap enrollment."""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import settings as settings_mod

TOKEN_FILE = "device_bootstrap_token.json"
_token_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def token_path() -> Path:
    return settings_mod.settings.keys_dir / TOKEN_FILE


def ensure_device_bootstrap_token() -> str:
    """Create or return the current unconsumed local-device bootstrap token."""
    with _token_lock:
        settings_mod.settings.ensure_dirs()
        path = token_path()
        data = _read_token(path)
        if data and not data.get("used_at") and _expires_at(data) > _now():
            return str(data["token"])

        token = secrets.token_urlsafe(32)
        expires_at = _now() + timedelta(seconds=settings_mod.settings.setup_token_ttl_seconds)
        _write_token(path, {"token": token, "expires_at": expires_at.isoformat(), "used_at": None})
        return token


def verify_and_consume_device_bootstrap_token(candidate: str | None) -> bool:
    if not candidate:
        return False
    with _token_lock:
        path = token_path()
        data = _read_token(path)
        if not data or data.get("used_at"):
            return False
        if _expires_at(data) <= _now():
            return False
        if not secrets.compare_digest(str(data["token"]), candidate.strip()):
            return False
        data["used_at"] = _now().isoformat()
        _write_token(path, data)
        return True


def _write_token(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def _read_token(path: Path) -> dict | None:
    try:
        raw = path.read_text("utf-8").strip()
        if raw.startswith("{"):
            return json.loads(raw)
        return {
            "token": raw,
            "expires_at": (
                _now() + timedelta(seconds=settings_mod.settings.setup_token_ttl_seconds)
            ).isoformat(),
            "used_at": None,
        }
    except Exception:
        return None


def _expires_at(data: dict) -> datetime:
    try:
        value = datetime.fromisoformat(str(data["expires_at"]))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)
