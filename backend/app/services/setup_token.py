"""One-time authorization token for first-run setup."""
from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app import settings as settings_mod

TOKEN_FILE = "setup_token.json"


def _now() -> datetime:
    return datetime.now(UTC)


def token_path() -> Path:
    return settings_mod.settings.keys_dir / TOKEN_FILE


def ensure_setup_token() -> str:
    """Create the setup token file if needed and return the current token.

    The token file is readable only by the backend service account/root/admins
    on supported platforms. It is consumed after successful first-admin setup.
    """
    settings_mod.settings.ensure_dirs()
    path = token_path()
    if path.exists():
        data = _read_token(path)
        if data and _expires_at(data) > _now():
            return str(data["token"])

    token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=settings_mod.settings.setup_token_ttl_seconds)
    path.write_text(
        json.dumps({"token": token, "expires_at": expires_at.isoformat()}),
        encoding="utf-8",
    )
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return token


def verify_setup_token(candidate: str | None) -> bool:
    if not candidate:
        return False
    data = _read_token(token_path())
    if not data:
        return False
    if _expires_at(data) <= _now():
        return False
    return secrets.compare_digest(str(data["token"]), candidate.strip())


def consume_setup_token() -> None:
    token_path().unlink(missing_ok=True)


def _read_token(path: Path) -> dict | None:
    try:
        raw = path.read_text("utf-8").strip()
        if raw.startswith("{"):
            return json.loads(raw)
        # Backward-compatible for installer-created plain-token files.
        return {
            "token": raw,
            "expires_at": (
                _now() + timedelta(seconds=settings_mod.settings.setup_token_ttl_seconds)
            ).isoformat(),
        }
    except Exception:
        return None


def _expires_at(data: dict) -> datetime:
    try:
        value = datetime.fromisoformat(str(data["expires_at"]))
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value
    except Exception:
        return datetime.fromtimestamp(0, tz=UTC)
