"""Service-owned Codex device authentication without exposing OAuth tokens."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

_URL_RE = re.compile(r"https://[^\s]+", re.I)
_CODE_RE = re.compile(r"\b[A-Z0-9]{4,}(?:-[A-Z0-9]{4,})+\b", re.I)
_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}


def _env(codex_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    return env


def status(*, executable: str, codex_home: Path) -> dict[str, Any]:
    resolved = shutil.which(executable) if not Path(executable).is_file() else executable
    if not resolved:
        return {"installed": False, "connected": False, "status": "not_installed"}
    try:
        result = subprocess.run(
            [str(resolved), "login", "status"],
            env=_env(codex_home),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"installed": True, "connected": False, "status": "unavailable"}
    connected = result.returncode == 0 and "logged in" in (result.stdout + result.stderr).lower()
    return {"installed": True, "connected": connected, "status": "connected" if connected else "not_connected"}


def start(*, executable: str, codex_home: Path) -> dict[str, Any]:
    current = status(executable=executable, codex_home=codex_home)
    if not current["installed"]:
        return current
    if current["connected"]:
        return {**current, "session_id": None}
    with _lock:
        for session in _sessions.values():
            if session["status"] in {"starting", "waiting"}:
                return public(session)
        session_id = uuid4().hex
        session = {
            "session_id": session_id,
            "status": "starting",
            "verification_url": None,
            "user_code": None,
            "created_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(minutes=10),
            "process": None,
        }
        _sessions[session_id] = session
    threading.Thread(target=_run, args=(session_id, str(shutil.which(executable) or executable), codex_home), daemon=True).start()
    return public(session)


def _run(session_id: str, executable: str, codex_home: Path) -> None:
    try:
        codex_home.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(codex_home, 0o700)
        process = subprocess.Popen(
            [executable, "login", "--device-auth"],
            env=_env(codex_home),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with _lock:
            _sessions[session_id]["process"] = process
        assert process.stdout is not None
        for line in process.stdout:
            with _lock:
                session = _sessions.get(session_id)
                if session is None:
                    process.terminate()
                    return
                if datetime.now(UTC) >= session["expires_at"]:
                    session["status"] = "expired"
                    process.terminate()
                    return
                url = _URL_RE.search(line)
                code = _CODE_RE.search(line)
                if url:
                    session["verification_url"] = url.group(0).rstrip(".,)")
                if code:
                    session["user_code"] = code.group(0)
                if url or code:
                    session["status"] = "waiting"
        return_code = process.wait(timeout=5)
        with _lock:
            session = _sessions.get(session_id)
            if session:
                session["status"] = "connected" if return_code == 0 else "failed"
                session["process"] = None
                session["verification_url"] = None
                session["user_code"] = None
    except Exception:
        with _lock:
            if session_id in _sessions:
                _sessions[session_id]["status"] = "failed"
                _sessions[session_id]["process"] = None


def get(session_id: str) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(session_id)
        return public(session) if session else None


def cancel(session_id: str) -> bool:
    with _lock:
        session = _sessions.get(session_id)
        if not session:
            return False
        process = session.get("process")
        session["status"] = "cancelled"
    if process and process.poll() is None:
        process.terminate()
    return True


def public(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session.get("session_id"),
        "status": session["status"],
        "verification_url": session.get("verification_url"),
        "user_code": session.get("user_code"),
        "expires_at": session.get("expires_at"),
    }
