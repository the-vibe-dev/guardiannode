"""Release-only recovery for restrictions created by older GuardianNode builds.

Screenshot-focused GuardianNode cannot suspend apps, add website blocks, or show
remote child prompts. This compatibility module only releases a recorded process
identity or removes an exact GuardianNode-owned hosts entry during upgrade.
Identity-less legacy PID records are preserved for operator recovery.
"""
from __future__ import annotations

import hashlib
import json
import math
import ntpath
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)
_STATE_VERSION = 2
# Retain completed compatibility receipts beyond the old delivery window.
# Unresolved process identities and PID-only records are never pruned.
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


class RecoveryStateError(RuntimeError):
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
    resumed: int = 0
    stale: int = 0
    uninspectable: int = 0
    removed_domain_entries: int = 0
    pending_domain_blocks: int = 0

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
        partial = bool(self.failed or self.protected or pending or legacy or self.pending_domain_blocks)
        return {
            "matched_processes": len(self.matched),
            "suspended_processes": len(self.suspended),
            "newly_suspended_processes": 0,
            "resumed_processes": self.resumed,
            "failed_processes": len(self.failed),
            "skipped_protected_processes": len(self.protected),
            "already_suspended_elsewhere": 0,
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
            "retryable": bool(self.failed or pending or self.pending_domain_blocks),
            "removed_domain_entries": self.removed_domain_entries,
            "pending_domain_blocks": self.pending_domain_blocks,
            # An inaccessible, unrelated executable cannot be identified as a
            # match. Do not falsely count it as a successfully checked process.
            "scan_complete": self.uninspectable == 0,
        }


class LegacyRestrictionRecovery:
    def __init__(self, state_path: Path | None = None, hosts_path: Path | None = None):
        self.state_path = state_path or default_state_path()
        self.hosts_path = hosts_path or default_hosts_path()

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        action = str(command.get("command_type") or "")
        if action != "undo_action":
            raise ValueError("restriction commands are unavailable in screenshot review mode")
        if not _is_windows():
            raise RuntimeError("legacy restriction recovery is supported only on Windows")
        command_id = str(command.get("command_id") or "")
        payload = command.get("payload") or {}
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", command_id) or not isinstance(payload, dict):
            raise ValueError("invalid device command")
        return self._undo(payload, command_id=command_id)

    def reconcile(self) -> dict[str, Any] | None:
        """Release every verifiable old restriction, regardless of its old expiry."""
        if not _is_windows():
            return None
        return self._release_state(self._load_state())

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
        # Never operate on service accounts or protected processes, even when
        # an old journal claims ownership. Unreadable identities stay pending.
        owner = process.username().casefold()
        return owner in {
            "nt authority\\system", "nt authority\\local service", "nt authority\\network service",
        } or owner.startswith("nt service\\")

    def _release_state(self, state: dict[str, Any]) -> dict[str, Any]:
        import psutil

        progress = _Progress()
        try:
            now = time.time()
            changed = False
            for command_id, item in list(state["actions"].items()):
                if item["type"] == "pause_app" and item["status"] == "active":
                    item.update(status="undone", completed_at=now)
                    changed = True
                if item.get("status") != "legacy_unverified" and item.get("completed_at", now) < now - _REPLAY_RETENTION_SECONDS:
                    del state["actions"][command_id]
                    changed = True
            # Persist release intent before any process operation. No new
            # process is ever discovered, adopted, or suspended.
            for record in state["processes"].values():
                if record["phase"] != "resume_pending":
                    record["phase"] = "resume_pending"
                    changed = True
            if changed:
                self._save_state(state)

            protected = self._protected_pids(psutil)
            for identity, record in list(state["processes"].items()):
                try:
                    process = psutil.Process(record["pid"])
                    if not self._same_process(process, record, psutil):
                        self._forget_process(state, identity)
                        progress.stale += 1
                        continue
                    progress.matched.add(identity)
                    if self._protected_process(process, record, protected):
                        progress.protected.add(record["pid"])
                        continue
                    if process.status() == psutil.STATUS_STOPPED:
                        progress.suspended.add(identity)
                        # Keep this Process object: psutil adds its PID-reuse
                        # guard at the OS boundary after our identity recheck.
                        if not self._same_process(process, record, psutil):
                            raise psutil.NoSuchProcess(record["pid"])
                        process.resume()
                        progress.resumed += 1
                        progress.suspended.discard(identity)
                    self._forget_process(state, identity)
                except psutil.NoSuchProcess:
                    self._forget_process(state, identity)
                    progress.stale += 1
                except (psutil.AccessDenied, ValueError, OSError):
                    progress.failed.add(identity)
                    progress.uninspectable += 1

            domains = [item for item in state["actions"].values() if item["type"] == "block_domain" and item["status"] == "active"]
            try:
                # Old versions wrote hosts before their journal. Exact owned
                # entries may therefore survive with no corresponding record.
                progress.removed_domain_entries = self._remove_owned_hosts_entries()
            except OSError:
                # At least one unresolved cleanup attempt remains even if the
                # inaccessible hosts file contains only an orphaned old entry.
                progress.pending_domain_blocks = max(1, len(domains))
            else:
                for item in domains:
                    item.update(status="undone", completed_at=now)
                if domains:
                    self._save_state(state)
            return progress.result(state, None)
        except RecoveryStateError as exc:
            exc.result = {
                **progress.result(state, None), **exc.result,
                "partial_failure": True, "persistence_failed": True, "retryable": True,
            }
            raise

    def _forget_process(self, state: dict[str, Any], identity: str) -> None:
        record = state["processes"].pop(identity, None)
        try:
            self._save_state(state)
        except RecoveryStateError:
            if record is not None:
                state["processes"][identity] = record
            raise

    def _undo(self, payload: dict[str, Any], command_id: str) -> dict[str, Any]:
        original = str(payload.get("original_action") or "")
        if original not in {"pause_app", "block_domain"}:
            raise ValueError("undo target is not reversible")
        target = (
            validate_executable(payload.get("target")) if original == "pause_app"
            else validate_domain(payload.get("target"))
        )
        key = _executable_key(target) if original == "pause_app" else target
        original_id = payload.get("original_command_id")
        if original_id is not None and (
            not isinstance(original_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", original_id)
        ):
            raise ValueError("original command ID is invalid")
        state = self._load_state()
        previous = state["actions"].get(command_id)
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
                if item["type"] == original and item["status"] in {"active", "undone", "expired", "legacy_unverified"}
                and (_executable_key(item["target"]) if original == "pause_app" else item["target"]) == key
                and (original_id is None or item_id == original_id)
            ]
            state["actions"][command_id] = {
                "type": "undo_action", "original_action": original, "target": key,
                "original_command_id": original_id, "undone_commands": ids,
                "status": "completed", "completed_at": time.time(),
            }
            self._save_state(state)
        context = {
            "undone": len(ids), "original_action": original,
            "idempotent_replay": previous is not None,
        }
        try:
            # An explicit compatibility Undo also reconciles all older owned
            # restrictions. None are kept alive by screenshot review mode.
            result = self._release_state(state)
        except RecoveryStateError as exc:
            exc.result.update(context)
            raise
        return {**context, **result}

    @staticmethod
    def _is_owned_hosts_line(line: bytes) -> bool:
        try:
            value = line.rstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError:
            return False
        match = re.fullmatch(
            r"(?:127\.0\.0\.1|::1)[ \t]+([^ \t]+)[ \t]+# GuardianNode ([A-Za-z0-9_-]{1,128})[ \t]*",
            value,
        )
        if not match:
            return False
        try:
            return validate_domain(match.group(1)) == match.group(1)
        except ValueError:
            return False

    def _remove_owned_hosts_entries(self) -> int:
        """Remove exact legacy marker lines, preserving every unrelated byte."""
        try:
            before = self.hosts_path.read_bytes()
        except FileNotFoundError:
            return 0
        lines = before.splitlines(keepends=True)
        retained = [line for line in lines if not self._is_owned_hosts_line(line)]
        removed = len(lines) - len(retained)
        if not removed:
            return 0
        temporary: str | None = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix="hosts.guardiannode-", suffix=".tmp", dir=self.hosts_path.parent)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(b"".join(retained))
                stream.flush()
                os.fsync(stream.fileno())
            shutil.copymode(self.hosts_path, temporary)
            # Do not overwrite an editor's intervening change. A later control
            # poll retries against its fresh bytes.
            if self.hosts_path.read_bytes() != before:
                raise OSError("hosts file changed during legacy recovery")
            os.replace(temporary, self.hosts_path)
            return removed
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text("utf-8"))
        except FileNotFoundError:
            return _empty_state()
        except (OSError, ValueError) as exc:
            raise RecoveryStateError("legacy restriction state is unreadable; preserved for recovery") from exc
        try:
            if not isinstance(value, dict):
                raise ValueError("state is not an object")
            if "version" not in value:
                value = self._migrate_legacy(value)
            self._validate_state(value)
            return value
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RecoveryStateError("legacy restriction state is invalid; preserved for recovery") from exc

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
            if not isinstance(command_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", command_id) or not isinstance(item, dict):
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
            raise RecoveryStateError("could not persist legacy restriction recovery state") from exc
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
