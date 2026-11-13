"""Reversible, explicitly parent-confirmed actions executed by the Windows broker.

The journal is in the broker's protected directory. Process ownership is shared
between leases, and always includes PID, creation time and executable. No process
operation is permitted on a PID recovered from the old, identity-less format.
"""
from __future__ import annotations

import hashlib
import json
import math
import ntpath
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)
_MARKER = "# GuardianNode "
_STATE_VERSION = 2
# Backend commands expire after 24 hours. Keep completed identities longer than
# that delivery window so a lost acknowledgement cannot reapply an old pause.
_REPLAY_RETENTION_SECONDS = 7 * 86400
_PROTECTED_NAMES = frozenset({
    "system", "system idle process", "registry", "memory compression",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "lsaiso.exe", "svchost.exe", "fontdrvhost.exe", "dwm.exe",
    "explorer.exe", "sihost.exe", "taskhostw.exe", "conhost.exe",
    "securityhealthservice.exe", "securityhealthsystray.exe", "msmpeng.exe",
    "mpcmdrun.exe", "nissrv.exe", "audiodg.exe", "spoolsv.exe",
})


def default_state_path() -> Path:
    from src.broker_service import default_secure_dir

    return default_secure_dir() / "enforcement_state.json"


def default_hosts_path() -> Path:
    return Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "drivers" / "etc" / "hosts"


def _is_windows() -> bool:
    return os.name == "nt"


def validate_executable(value: object) -> str:
    raw = str(value or "").strip()
    parsed = PureWindowsPath(raw)
    if (
        not raw or not parsed.is_absolute() or ".." in parsed.parts
        or parsed.suffix.lower() != ".exe" or any(ord(char) < 32 for char in raw)
    ):
        raise ValueError("pause_app target must be an exact absolute .exe path")
    return str(parsed)


def _executable_key(value: str) -> str:
    # Use Windows semantics even in portable tests and when reading old state.
    return ntpath.normcase(ntpath.normpath(value))


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


def _identity_key(record: dict[str, Any]) -> str:
    encoded = json.dumps(
        [record["pid"], record["create_time"], record["exe"]], separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _empty_state() -> dict[str, Any]:
    return {"version": _STATE_VERSION, "actions": {}, "processes": {}}


class EnforcementStateError(RuntimeError):
    """Persistence failed; optional result preserves truthful partial outcomes."""

    def __init__(self, message: str, *, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.result = result or {}


@dataclass
class _Progress:
    matched: set[str] = field(default_factory=set)
    suspended: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    protected: set[int] = field(default_factory=set)
    external: set[str] = field(default_factory=set)
    newly_suspended: int = 0
    resumed: int = 0
    stale: int = 0
    uninspectable: int = 0

    def result(self, state: dict[str, Any], target: str | None) -> dict[str, Any]:
        records = [
            item for item in state["processes"].values()
            if target is None or item["exe"] == target
        ]
        legacy = sum(
            len(item.get("legacy_pids", [])) for item in state["actions"].values()
            if item.get("status") == "legacy_unverified"
            and (target is None or _executable_key(item["target"]) == target)
        )
        pending = sum(item["phase"] == "resume_pending" for item in records)
        partial = bool(self.failed or self.protected or pending or legacy)
        return {
            "matched_processes": len(self.matched),
            "suspended_processes": len(self.suspended),
            "newly_suspended_processes": self.newly_suspended,
            "resumed_processes": self.resumed,
            "failed_processes": len(self.failed),
            "skipped_protected_processes": len(self.protected),
            "already_suspended_elsewhere": len(self.external),
            "uninspectable_processes": self.uninspectable,
            "stale_process_records": self.stale,
            "pending_resume_processes": pending,
            "pending_recovery_processes": sum(item["phase"] != "suspended" for item in records),
            "legacy_unverified_processes": legacy,
            "active_pause_leases": sum(
                item["type"] == "pause_app" and item["status"] == "active"
                and (target is None or _executable_key(item["target"]) == target)
                for item in state["actions"].values()
            ),
            "partial_failure": partial,
            "retryable": bool(self.failed or pending),
            # An inaccessible, unrelated executable cannot be identified as a
            # match. Do not falsely count it as a successfully checked process.
            "scan_complete": self.uninspectable == 0,
        }


class WindowsEnforcer:
    def __init__(self, state_path: Path | None = None, hosts_path: Path | None = None):
        self.state_path = state_path or default_state_path()
        self.hosts_path = hosts_path or default_hosts_path()

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        if not _is_windows():
            raise RuntimeError("device enforcement is supported only on Windows")
        command_id = str(command.get("command_id") or "")
        action = str(command.get("command_type") or "")
        payload = command.get("payload") or {}
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", command_id) or not isinstance(payload, dict):
            raise ValueError("invalid device command")
        if action == "pause_app":
            return self._pause_app(command_id, payload)
        if action == "block_domain":
            return self._block_domain(command_id, payload)
        if action == "show_child_prompt":
            return self._show_prompt(payload)
        if action == "undo_action":
            return self._undo(payload, command_id=command_id)
        raise ValueError("unsupported device command")

    def reconcile(self) -> dict[str, Any] | None:
        if not _is_windows():
            return None
        return self._reconcile_state(self._load_state())

    @staticmethod
    def _protected_target(target: str) -> bool:
        name = ntpath.basename(target).lower()
        return (
            name in _PROTECTED_NAMES or name.startswith("guardiannode")
            or _executable_key(target) == _executable_key(sys.executable)
        )

    @staticmethod
    def _protected_pids(psutil: Any) -> set[int]:
        protected = {0, 4, os.getpid()}
        try:
            protected.update(process.pid for process in psutil.Process(os.getpid()).parents())
        except (psutil.Error, OSError):
            # Names and the current PID remain protected if ancestry cannot be read.
            pass
        return protected

    @staticmethod
    def _identity(process: Any, psutil: Any) -> dict[str, Any]:
        if not process.is_running():
            raise psutil.NoSuchProcess(process.pid)
        created = float(process.create_time())
        executable = validate_executable(process.exe())
        if not math.isfinite(created) or created <= 0:
            raise ValueError("process creation time is unavailable")
        return {"pid": int(process.pid), "create_time": created, "exe": _executable_key(executable)}

    def _same_process(self, process: Any, record: dict[str, Any], psutil: Any) -> bool:
        return self._identity(process, psutil) == {
            key: record[key] for key in ("pid", "create_time", "exe")
        }

    def _protected_process(self, process: Any, record: dict[str, Any], protected: set[int]) -> bool:
        if record["pid"] in protected or self._protected_target(record["exe"]):
            return True
        # The broker may act on ordinary user applications, never Windows
        # service accounts. If ownership cannot be read, the caller skips it.
        owner = process.username().casefold()
        return owner in {
            "nt authority\\system", "nt authority\\local service", "nt authority\\network service",
        } or owner.startswith("nt service\\")

    def _pause_app(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        target = validate_executable(payload.get("target"))
        key = _executable_key(target)
        duration = int(payload.get("duration_seconds") or 0)
        if duration not in {900, 3600, 86400}:
            raise ValueError("pause_app duration is not allowed")
        if self._protected_target(target):
            raise ValueError("system, security and GuardianNode processes cannot be paused")
        state = self._load_state()
        item = state["actions"].get(command_id)
        replay = item is not None
        if item is not None:
            if (
                item["type"] != "pause_app" or _executable_key(item["target"]) != key
                or (item.get("duration_seconds") not in (None, duration))
            ):
                raise ValueError("command ID already belongs to a different action")
        else:
            now = time.time()
            item = {
                "type": "pause_app", "target": target, "duration_seconds": duration,
                "created_at": now, "expires_at": now + duration, "status": "active",
            }
            state["actions"][command_id] = item
            # A durable parent lease must exist before any process operation.
            self._save_state(state)
        context = {
            "target": target, "duration_seconds": duration,
            "expires_at": item["expires_at"], "idempotent_replay": replay,
        }
        try:
            result = self._reconcile_state(state, target=key)
        except EnforcementStateError as exc:
            exc.result.update(context, lease_status=item["status"])
            raise
        return {**context, "lease_status": item["status"], **result}

    def _reconcile_state(self, state: dict[str, Any], target: str | None = None) -> dict[str, Any]:
        import psutil

        progress = _Progress()
        try:
            now = time.time()
            changed = False
            for command_id, item in list(state["actions"].items()):
                if item["type"] == "pause_app" and item["status"] == "active" and item["expires_at"] <= now:
                    item.update(status="expired", completed_at=now)
                    changed = True
                if item.get("completed_at", now) < now - _REPLAY_RETENTION_SECONDS:
                    del state["actions"][command_id]
                    changed = True
            if changed:
                self._save_state(state)
            active = {
                _executable_key(item["target"]) for item in state["actions"].values()
                if item["type"] == "pause_app" and item["status"] == "active"
                and (target is None or _executable_key(item["target"]) == target)
            }
            protected = self._protected_pids(psutil)
            seen: set[int] = set()
            for identity, record in list(state["processes"].items()):
                if target is not None and record["exe"] != target:
                    continue
                seen.add(record["pid"])
                # Persist release intent before attempting it. AccessDenied must
                # leave a retryable identity, including across broker restarts.
                if record["exe"] not in active and record["phase"] != "resume_pending":
                    record["phase"] = "resume_pending"
                    self._save_state(state)
                try:
                    process = psutil.Process(record["pid"])
                    if not self._same_process(process, record, psutil):
                        self._forget_process(state, identity)
                        progress.stale += 1
                        seen.discard(record["pid"])
                        continue
                    progress.matched.add(identity)
                    if self._protected_process(process, record, protected):
                        progress.protected.add(record["pid"])
                        continue
                    stopped = process.status() == psutil.STATUS_STOPPED
                    if record["exe"] not in active:
                        if stopped:
                            # psutil also checks PID reuse immediately before its
                            # OS call; keep the same Process object for that guard.
                            if not self._same_process(process, record, psutil):
                                raise psutil.NoSuchProcess(record["pid"])
                            process.resume()
                            progress.resumed += 1
                        self._forget_process(state, identity)
                    elif stopped:
                        # A persisted pre-suspend intent survives an interruption
                        # between the OS call and recording its completion. A new
                        # active lease also cancels an older failed release: never
                        # resume an owned suspension while another lease needs it.
                        if record["phase"] != "suspended":
                            record["phase"] = "suspended"
                            self._save_state(state)
                        progress.suspended.add(identity)
                    else:
                        self._suspend_process(state, identity, record, process, psutil, progress)
                except psutil.NoSuchProcess:
                    self._forget_process(state, identity)
                    progress.stale += 1
                    seen.discard(record["pid"])
                except (psutil.AccessDenied, ValueError, OSError):
                    progress.failed.add(identity)

            if active:
                for candidate in psutil.process_iter(["pid", "exe"]):
                    if candidate.pid in seen:
                        continue
                    executable = candidate.info.get("exe")
                    if not executable:
                        if candidate.pid not in protected:
                            progress.uninspectable += 1
                        continue
                    executable = _executable_key(str(executable))
                    if executable not in active:
                        continue
                    if candidate.pid in protected or self._protected_target(executable):
                        progress.protected.add(candidate.pid)
                        continue
                    failed_key = f"pid:{candidate.pid}"
                    try:
                        # process_iter can cache Process objects; bind a new
                        # object and re-read identity before claiming ownership.
                        process = psutil.Process(candidate.pid)
                        record = self._identity(process, psutil)
                        if record["exe"] not in active:
                            continue
                        identity = _identity_key(record)
                        failed_key = identity
                        progress.matched.add(identity)
                        if self._protected_process(process, record, protected):
                            progress.protected.add(record["pid"])
                            continue
                        if process.status() == psutil.STATUS_STOPPED:
                            # Never adopt and later resume somebody else's pause.
                            progress.external.add(identity)
                            continue
                        self._suspend_process(state, identity, record, process, psutil, progress)
                    except psutil.NoSuchProcess:
                        continue
                    except (psutil.AccessDenied, ValueError, OSError):
                        progress.failed.add(failed_key)
            return progress.result(state, target)
        except EnforcementStateError as exc:
            exc.result = {
                **progress.result(state, target), **exc.result,
                "partial_failure": True, "persistence_failed": True, "retryable": True,
            }
            raise

    def _suspend_process(
        self, state: dict[str, Any], identity: str, record: dict[str, Any],
        process: Any, psutil: Any, progress: _Progress,
    ) -> None:
        record["phase"] = "suspend_pending"
        state["processes"][identity] = record
        # Full identity and resume intent reach disk BEFORE suspension. If this
        # write fails there is no OS side effect to roll back.
        try:
            self._save_state(state)
        except EnforcementStateError:
            progress.failed.add(identity)
            raise
        try:
            if not self._same_process(process, record, psutil):
                raise psutil.NoSuchProcess(record["pid"])
            process.suspend()
        except (psutil.AccessDenied, OSError) as exc:
            # A failing OS call could have affected some threads. Attempt release
            # and retain the identity if the release cannot be confirmed.
            record["phase"] = "resume_pending"
            progress.failed.add(identity)
            released, persisted = self._rollback_suspend(state, identity, record, process, psutil)
            if not persisted:
                raise EnforcementStateError(
                    "suspension failed and recovery journal could not be updated",
                    result={"rollback_succeeded": released},
                ) from exc
            raise
        record["phase"] = "suspended"
        try:
            self._save_state(state)
        except EnforcementStateError as exc:
            # The write-ahead record still exists on disk. Resume the exact
            # process immediately; if that fails, recovery has its identity.
            rolled_back, _ = self._rollback_suspend(state, identity, record, process, psutil)
            progress.failed.add(identity)
            exc.result["rollback_succeeded"] = rolled_back
            raise
        progress.suspended.add(identity)
        progress.newly_suspended += 1

    def _rollback_suspend(
        self, state: dict[str, Any], identity: str, record: dict[str, Any], process: Any, psutil: Any,
    ) -> tuple[bool, bool]:
        record["phase"] = "resume_pending"
        released = False
        try:
            if self._same_process(process, record, psutil):
                process.resume()
            released = True
        except psutil.NoSuchProcess:
            released = True
        except (psutil.AccessDenied, ValueError, OSError):
            pass
        if released:
            state["processes"].pop(identity, None)
        try:
            self._save_state(state)
        except EnforcementStateError:
            # The previous, durable suspend_pending identity remains a recovery
            # record. Never erase it or replace corrupt state with an empty file.
            record["phase"] = "suspend_pending"
            state["processes"][identity] = record
            return released, False
        return released, True

    def _forget_process(self, state: dict[str, Any], identity: str) -> None:
        record = state["processes"].pop(identity, None)
        try:
            self._save_state(state)
        except EnforcementStateError:
            if record is not None:
                state["processes"][identity] = record
            raise

    def _block_domain(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        domain = validate_domain(payload.get("target"))
        state = self._load_state()
        existing = state["actions"].get(command_id)
        if existing is not None:
            if existing["type"] != "block_domain" or existing["target"] != domain:
                raise ValueError("command ID already belongs to a different action")
            return {"target": domain, "blocked": existing["status"] == "active", "idempotent_replay": True}
        lines = self.hosts_path.read_text("utf-8", errors="replace").splitlines()
        marker = f"{_MARKER}{command_id}"
        lines.extend([f"127.0.0.1 {domain} {marker}", f"::1 {domain} {marker}"])
        self._write_hosts(lines)
        state["actions"][command_id] = {"type": "block_domain", "target": domain, "status": "active"}
        self._save_state(state)
        return {"target": domain, "blocked": True}

    @staticmethod
    def _show_prompt(payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message") or "").strip()
        if not message or len(message) > 500:
            raise ValueError("child prompt message is invalid")
        subprocess.run(
            ["msg.exe", "*", "/TIME:60", message],
            check=True, timeout=15, creationflags=0x08000000,
        )
        return {"shown": True}

    def _undo(self, payload: dict[str, Any], command_id: str | None = None) -> dict[str, Any]:
        original = str(payload.get("original_action") or "")
        if original not in {"pause_app", "block_domain"}:
            raise ValueError("undo target is not reversible")
        target = (
            validate_executable(payload.get("target")) if original == "pause_app"
            else validate_domain(payload.get("target"))
        )
        key = _executable_key(target) if original == "pause_app" else target
        original_id = payload.get("original_command_id")
        if original_id is not None and (not isinstance(original_id, str) or not original_id):
            raise ValueError("original command ID is invalid")
        state = self._load_state()
        previous = state["actions"].get(command_id) if command_id else None
        if previous is not None:
            if (
                previous["type"] != "undo_action" or previous["original_action"] != original
                or previous["target"] != key or previous.get("original_command_id") != original_id
            ):
                raise ValueError("command ID already belongs to a different action")
            ids = previous["undone_commands"]
        else:
            ids = [
                item_id for item_id, item in state["actions"].items()
                if item["type"] == original and item["status"] == "active"
                and (_executable_key(item["target"]) if original == "pause_app" else item["target"]) == key
                and (original_id is None or item_id == original_id)
            ]
            for item_id in ids:
                state["actions"][item_id].update(status="undone", completed_at=time.time())
            if command_id:
                state["actions"][command_id] = {
                    "type": "undo_action", "original_action": original, "target": key,
                    "original_command_id": original_id, "undone_commands": ids,
                    "status": "completed", "completed_at": time.time(),
                }
            if original == "pause_app":
                # Losing an undo acknowledgement must never reactivate a pause.
                self._save_state(state)
        context = {
            "undone": len(ids), "original_action": original,
            "idempotent_replay": previous is not None,
        }
        if original == "block_domain":
            markers = {f"{_MARKER}{item_id}" for item_id in ids}
            lines = [
                line for line in self.hosts_path.read_text("utf-8", errors="replace").splitlines()
                if not any(line.rstrip().endswith(marker) for marker in markers)
            ]
            self._write_hosts(lines)
            self._save_state(state)
            result: dict[str, Any] = {}
        else:
            try:
                result = self._reconcile_state(state, target=key)
            except EnforcementStateError as exc:
                exc.result.update(context)
                raise
        return {**context, **result}

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text("utf-8"))
        except FileNotFoundError:
            return _empty_state()
        except (OSError, ValueError) as exc:
            raise EnforcementStateError("enforcement state is unreadable; preserved for recovery") from exc
        try:
            if not isinstance(value, dict):
                raise ValueError("state is not an object")
            if "version" not in value:
                value = self._migrate_legacy(value)
            self._validate_state(value)
            return value
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise EnforcementStateError("enforcement state is invalid; preserved for recovery") from exc

    @staticmethod
    def _migrate_legacy(value: dict[str, Any]) -> dict[str, Any]:
        state = _empty_state()
        for command_id, old in value.items():
            if not isinstance(old, dict):
                raise ValueError("invalid legacy action")
            if old.get("type") == "pause_app":
                pids = old.get("pids", [])
                if not isinstance(pids, list) or any(type(pid) is not int or pid <= 0 for pid in pids):
                    raise ValueError("invalid legacy PID list")
                state["actions"][command_id] = {
                    "type": "pause_app", "target": validate_executable(old.get("target")),
                    "expires_at": old["expires_at"], "status": "legacy_unverified",
                    "legacy_pids": pids,
                }
            elif old.get("type") == "block_domain":
                state["actions"][command_id] = {
                    "type": "block_domain", "target": validate_domain(old.get("target")), "status": "active",
                }
            else:
                raise ValueError("unsupported legacy action")
        return state

    @staticmethod
    def _validate_state(state: dict[str, Any]) -> None:
        if state.get("version") != _STATE_VERSION:
            raise ValueError("unsupported enforcement state version")
        if not isinstance(state.get("actions"), dict) or not isinstance(state.get("processes"), dict):
            raise ValueError("invalid journal collections")
        for command_id, item in state["actions"].items():
            if not isinstance(command_id, str) or not command_id or not isinstance(item, dict):
                raise ValueError("invalid action record")
            action = item["type"]
            if action == "pause_app":
                validate_executable(item["target"])
                if item["status"] not in {"active", "expired", "undone", "legacy_unverified"}:
                    raise ValueError("invalid pause status")
                if type(item["expires_at"]) not in (float, int) or not math.isfinite(item["expires_at"]):
                    raise ValueError("invalid lease expiry")
                if item["status"] == "legacy_unverified" and not isinstance(item.get("legacy_pids"), list):
                    raise ValueError("invalid legacy record")
            elif action == "block_domain":
                validate_domain(item["target"])
                if item["status"] not in {"active", "undone"}:
                    raise ValueError("invalid block status")
            elif action == "undo_action":
                if (
                    item["status"] != "completed" or item["original_action"] not in {"pause_app", "block_domain"}
                    or not isinstance(item["undone_commands"], list)
                ):
                    raise ValueError("invalid undo record")
                if item["original_action"] == "pause_app":
                    validate_executable(item["target"])
                else:
                    validate_domain(item["target"])
                if any(not isinstance(command, str) or not command for command in item["undone_commands"]):
                    raise ValueError("invalid undo command list")
                original_id = item.get("original_command_id")
                if original_id is not None and (not isinstance(original_id, str) or not original_id):
                    raise ValueError("invalid undo identity")
            else:
                raise ValueError("unsupported action record")
            if "completed_at" in item and (
                type(item["completed_at"]) not in (float, int) or not math.isfinite(item["completed_at"])
            ):
                raise ValueError("invalid completion time")
        for identity, record in state["processes"].items():
            if (
                not isinstance(record, dict) or type(record["pid"]) is not int or record["pid"] <= 0
                or type(record["create_time"]) not in (float, int)
                or not math.isfinite(record["create_time"]) or record["create_time"] <= 0
                or record["phase"] not in {"suspend_pending", "suspended", "resume_pending"}
                or _executable_key(validate_executable(record["exe"])) != record["exe"]
                or _identity_key(record) != identity
            ):
                raise ValueError("invalid process identity")

    def _save_state(self, state: dict[str, Any]) -> None:
        temporary: str | None = None
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary = tempfile.mkstemp(prefix="enforcement-", suffix=".tmp", dir=self.state_path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(state, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state_path)
        except (OSError, ValueError, TypeError) as exc:
            raise EnforcementStateError("could not persist enforcement recovery state") from exc
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def _write_hosts(self, lines: list[str]) -> None:
        temporary = self.hosts_path.with_name("hosts.guardiannode.tmp")
        temporary.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        os.replace(temporary, self.hosts_path)
