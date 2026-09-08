"""Reversible, parent-confirmed Windows actions executed by the SYSTEM broker."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path, PureWindowsPath
from typing import Any

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)
_MARKER = "# GuardianNode "


def default_state_path() -> Path:
    from src.broker_service import default_secure_dir

    return default_secure_dir() / "enforcement_state.json"


def default_hosts_path() -> Path:
    return Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "drivers" / "etc" / "hosts"


def validate_executable(value: object) -> str:
    raw = str(value or "").strip()
    parsed = PureWindowsPath(raw)
    if not raw or not parsed.is_absolute() or ".." in parsed.parts or parsed.suffix.lower() != ".exe":
        raise ValueError("pause_app target must be an exact absolute .exe path")
    return str(parsed)


def validate_domain(value: object) -> str:
    raw = str(value or "").strip().rstrip(".").lower()
    if any(mark in raw for mark in ("://", "/", "*", "@")):
        raise ValueError("block_domain target must be one exact FQDN")
    try:
        domain = raw.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("block_domain target is invalid") from exc
    if not _DOMAIN_RE.fullmatch(domain):
        raise ValueError("block_domain target must be one exact FQDN")
    return domain


class WindowsEnforcer:
    def __init__(self, state_path: Path | None = None, hosts_path: Path | None = None):
        self.state_path = state_path or default_state_path()
        self.hosts_path = hosts_path or default_hosts_path()

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        if os.name != "nt":
            raise RuntimeError("device enforcement is supported only on Windows")
        command_id = str(command.get("command_id") or "")
        action = str(command.get("command_type") or "")
        payload = command.get("payload") or {}
        if not command_id or not isinstance(payload, dict):
            raise ValueError("invalid device command")
        if action == "pause_app":
            return self._pause_app(command_id, payload)
        if action == "block_domain":
            return self._block_domain(command_id, payload)
        if action == "show_child_prompt":
            return self._show_prompt(payload)
        if action == "undo_action":
            return self._undo(payload)
        raise ValueError("unsupported device command")

    def reconcile(self) -> None:
        if os.name != "nt":
            return
        state = self._load_state()
        changed = False
        now = int(time.time())
        for command_id, item in list(state.items()):
            if item.get("type") == "pause_app" and int(item.get("expires_at") or 0) <= now:
                self._resume_item(item)
                state.pop(command_id, None)
                changed = True
        if changed:
            self._save_state(state)

    def _pause_app(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        import psutil

        target = validate_executable(payload.get("target"))
        duration = int(payload.get("duration_seconds") or 0)
        if duration not in {900, 3600, 86400}:
            raise ValueError("pause_app duration is not allowed")
        state = self._load_state()
        if command_id in state:
            item = state[command_id]
            return {
                "target": target,
                "suspended_processes": len(item.get("pids") or []),
                "duration_seconds": duration,
                "idempotent_replay": True,
            }
        pids: list[int] = []
        for process in psutil.process_iter(["pid", "exe"]):
            try:
                executable = str(process.info.get("exe") or "")
                if executable and os.path.normcase(executable) == os.path.normcase(target):
                    process.suspend()
                    pids.append(int(process.pid))
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        state[command_id] = {
            "type": "pause_app",
            "target": target,
            "pids": pids,
            "expires_at": int(time.time()) + duration,
        }
        self._save_state(state)
        return {"target": target, "suspended_processes": len(pids), "duration_seconds": duration}

    def _block_domain(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        domain = validate_domain(payload.get("target"))
        state = self._load_state()
        if command_id in state:
            return {"target": domain, "blocked": True, "idempotent_replay": True}
        lines = self.hosts_path.read_text("utf-8", errors="replace").splitlines()
        marker = f"{_MARKER}{command_id}"
        lines.extend([f"127.0.0.1 {domain} {marker}", f"::1 {domain} {marker}"])
        self._write_hosts(lines)
        state[command_id] = {"type": "block_domain", "target": domain}
        self._save_state(state)
        return {"target": domain, "blocked": True}

    @staticmethod
    def _show_prompt(payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message") or "").strip()
        if not message or len(message) > 500:
            raise ValueError("child prompt message is invalid")
        subprocess.run(
            ["msg.exe", "*", "/TIME:60", message],
            check=True,
            timeout=15,
            creationflags=0x08000000,
        )
        return {"shown": True}

    def _undo(self, payload: dict[str, Any]) -> dict[str, Any]:
        original = str(payload.get("original_action") or "")
        state = self._load_state()
        removed = 0
        if original == "pause_app":
            target = validate_executable(payload.get("target"))
            for command_id, item in list(state.items()):
                if item.get("type") == "pause_app" and item.get("target") == target:
                    self._resume_item(item)
                    state.pop(command_id, None)
                    removed += 1
        elif original == "block_domain":
            target = validate_domain(payload.get("target"))
            ids = {
                command_id
                for command_id, item in state.items()
                if item.get("type") == "block_domain" and item.get("target") == target
            }
            lines = [
                line for line in self.hosts_path.read_text("utf-8", errors="replace").splitlines()
                if not any(f"{_MARKER}{command_id}" in line for command_id in ids)
            ]
            self._write_hosts(lines)
            for command_id in ids:
                state.pop(command_id, None)
            removed = len(ids)
        else:
            raise ValueError("undo target is not reversible")
        self._save_state(state)
        return {"undone": removed, "original_action": original}

    @staticmethod
    def _resume_item(item: dict[str, Any]) -> None:
        import psutil

        for pid in item.get("pids") or []:
            try:
                psutil.Process(int(pid)).resume()
            except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError):
                continue

    def _load_state(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.state_path.read_text("utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _save_state(self, state: dict[str, dict[str, Any]]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        temporary.replace(self.state_path)

    def _write_hosts(self, lines: list[str]) -> None:
        temporary = self.hosts_path.with_name("hosts.guardiannode.tmp")
        temporary.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        os.replace(temporary, self.hosts_path)
