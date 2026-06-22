"""Parent credential hashing helpers for the agent side.

The alpha tray pause flow accepts the parent password only. Recovery codes are
stored here for future migration/repair flows but do not authorize local tray
pause or exit actions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def _credentials_path() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "GuardianNode" / "parent.json"
    return Path.home() / ".guardiannode" / "parent.json"


def write_credentials(password: str, recovery_code: str, path: Path | None = None) -> None:
    p = path or _credentials_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "password_hash": _PH.hash(password),
        "recovery_hash": _PH.hash(" ".join(recovery_code.lower().split())),
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    tmp.replace(p)


def _load(path: Path | None) -> dict | None:
    p = path or _credentials_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def verify_password(password: str, path: Path | None = None) -> bool:
    data = _load(path)
    if not data:
        return False
    try:
        return _PH.verify(data["password_hash"], password)
    except (VerifyMismatchError, Exception):
        return False


def verify_recovery_code(code: str, path: Path | None = None) -> bool:
    data = _load(path)
    if not data:
        return False
    normalized = " ".join(code.lower().split())
    try:
        return _PH.verify(data["recovery_hash"], normalized)
    except (VerifyMismatchError, Exception):
        return False
