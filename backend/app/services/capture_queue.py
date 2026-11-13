"""Bounded capture housekeeping and durable, explicitly requested deletion.

Normal retention only visits the dead-letter directory. Withdrawal records
the exact generated frame tokens before revocation commits; a later consent
grant never broadens that deletion request to newly captured frames. State
lives in the existing settings table and contains no capture content.
"""
from __future__ import annotations

import json
import os
import re
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.orm import Session
from ulid import ULID

from app import settings as settings_mod
from app.db.models import Event, EvidenceBlob, Setting
from app.services import consent

DEFAULT_POLICY = {
    "dead_letter_retention_days": 7,
    "dead_letter_max_bytes": 256 * 1024 * 1024,
    "cleanup_batch_files": 256,
}
POLICY_BOUNDS = {
    "dead_letter_retention_days": (1, 90),
    "dead_letter_max_bytes": (1024 * 1024, 4 * 1024 * 1024 * 1024),
    "cleanup_batch_files": (1, 1000),
}
POLICY_KEY = "capture_queue_policy"
STATUS_KEY = "capture_queue_cleanup_status"
WITHDRAWAL_KEY = "capture_queue_withdrawal"
MAX_SCAN_ENTRIES = 10_000
MAX_TARGETS = 20_000
MAX_TARGET_STAT_CHECKS = 4096
DIRECTORIES = ("pending", "pending_dead_letter")
TOKEN_PATTERN = r"[0-9A-HJKMNP-TV-Z]{26}"
CAPTURE_FILE_RE = re.compile(
    rf"(?:{TOKEN_PATTERN}\.(?:enc|json)|"
    rf"\.{TOKEN_PATTERN}\.(?:enc|json)\.{TOKEN_PATTERN}\.tmp)\Z", re.IGNORECASE,
)
_TOKEN_RE = re.compile(rf"{TOKEN_PATTERN}\Z", re.IGNORECASE)
file_lock = threading.RLock()
_P = ParamSpec("_P")
_T = TypeVar("_T")
_scan_root: Path | None = None
_scan_cursors: dict[str, Any] = {}


def serialized(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Serialize short filesystem mutations, never classification/network IO."""
    @wraps(fn)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        with file_lock:
            return fn(*args, **kwargs)
    return wrapped


def capture_directory(name: str, *, create: bool = False) -> Path:
    if name not in DIRECTORIES:
        raise ValueError("unknown capture directory")
    root = settings_mod.settings.data_dir.resolve()
    path = root / name
    if path.is_symlink():
        raise OSError("unsafe capture directory")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if path.exists() and (not path.is_dir() or path.resolve() != path):
        raise OSError("unsafe capture directory")
    return path


@dataclass(frozen=True)
class CaptureFile:
    directory: str
    name: str
    size: int
    mtime: float

    @property
    def group(self) -> str:
        # A frame can move from pending to dead letter while deletion is queued.
        # Remember its token, so both locations and both halves stay in scope.
        return self.name if self.name.startswith(".") else self.name.rsplit(".", 1)[0]


@dataclass
class Inventory:
    files: list[CaptureFile] = field(default_factory=list)
    unsafe_files: int = 0
    scan_truncated: bool = False
    cycle_id: str | None = None
    cycle_complete: bool = False

    def public(self) -> dict[str, Any]:
        enc = {f.name[:-4] for f in self.files if f.name.endswith(".enc")}
        meta = {f.name[:-5] for f in self.files if f.name.endswith(".json")}
        oldest = min((f.mtime for f in self.files), default=None)
        try:
            oldest_at = datetime.fromtimestamp(oldest, UTC).isoformat() if oldest is not None else None
        except (ValueError, OverflowError, OSError):
            oldest_at = None
        return {
            "files": len(self.files), "frames": len(enc & meta),
            "bytes": sum(f.size for f in self.files), "oldest_at": oldest_at,
            "orphan_files": len(enc ^ meta) + sum(f.name.endswith(".tmp") for f in self.files),
            "unsafe_files": self.unsafe_files, "scan_truncated": self.scan_truncated,
        }


def inventory(name: str, *, work_scan: str | None = None) -> Inventory:
    """Read at most MAX_SCAN_ENTRIES directory entries, without file contents.

    Counts are observed lower bounds when truncated. Unrelated entries also
    consume scan budget, so a cluttered directory cannot monopolize a worker.
    """
    global _scan_root
    result = Inventory()
    entries = None
    cursor_key = f"{name}:{work_scan}"
    try:
        directory = capture_directory(name)
        if work_scan and _scan_root != directory.parent:
            for cursor in _scan_cursors.values():
                cursor[0].close()
            _scan_cursors.clear()
            _scan_root = directory.parent
        if not directory.exists():
            cursor = _scan_cursors.pop(cursor_key, None) if work_scan else None
            if cursor is not None:
                cursor[0].close()
            result.cycle_complete = True
            result.cycle_id = str(ULID()) if work_scan else None
            return result
        cursor = _scan_cursors.pop(cursor_key, None) if work_scan else None
        directory_info = directory.stat()
        identity = (directory_info.st_dev, directory_info.st_ino)
        if cursor is not None and cursor[2] != identity:
            cursor[0].close()
            cursor = None
        if cursor is not None:
            entries, result.cycle_id, _identity = cursor
            # A later window is still a partial inventory, even at directory end.
            result.scan_truncated = True
        else:
            entries = os.scandir(directory)
            if work_scan:
                result.cycle_id = str(ULID())
        exhausted = False
        for _index in range(MAX_SCAN_ENTRIES):
            try:
                entry = next(entries)
            except StopIteration:
                exhausted = True
                result.cycle_complete = True
                break
            if not CAPTURE_FILE_RE.fullmatch(entry.name):
                continue
            try:
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    result.unsafe_files += 1
                    continue
                result.files.append(CaptureFile(name, entry.name, info.st_size, info.st_mtime))
            except FileNotFoundError:
                continue
            except OSError:
                result.unsafe_files += 1
        if not exhausted:
            result.scan_truncated = True
            if work_scan:
                # Keep the directory iterator between bounded passes. Locked or
                # unrelated entries at the front cannot starve a later window.
                _scan_cursors[cursor_key] = (entries, result.cycle_id, identity)
                entries = None
    except OSError:
        cursor = _scan_cursors.pop(cursor_key, None) if work_scan else None
        if cursor is not None:
            cursor[0].close()
        result.unsafe_files += 1
        result.scan_truncated = True
    finally:
        if entries is not None:
            entries.close()
    return result


def _read(session: Session, key: str) -> dict[str, Any]:
    row = session.get(Setting, key)
    if row is None:
        return {}
    try:
        value = json.loads(row.value)
        if isinstance(value, dict):
            return value
    except (ValueError, TypeError):
        pass
    return {"inventory_incomplete": True, "state_invalid": True} if key == WITHDRAWAL_KEY else {}


def _write(session: Session, key: str, value: dict[str, Any]) -> None:
    row = session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value="{}")
        session.add(row)
    row.value = json.dumps(value, separators=(",", ":"), sort_keys=True)
    session.flush()


def get_policy(session: Session) -> dict[str, int]:
    saved = _read(session, POLICY_KEY)
    result = dict(DEFAULT_POLICY)
    for key, (minimum, maximum) in POLICY_BOUNDS.items():
        value = saved.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum:
            result[key] = value
    return result


def set_policy(session: Session, changes: dict[str, int]) -> dict[str, int]:
    for key, value in changes.items():
        bounds = POLICY_BOUNDS.get(key)
        if bounds is None or type(value) is not int or not bounds[0] <= value <= bounds[1]:
            raise ValueError("invalid capture cleanup policy")
    result = {**get_policy(session), **changes}
    _write(session, POLICY_KEY, result)
    return result


def _targets(state: dict[str, Any]) -> list[str]:
    raw = state.get("targets", [])
    if not isinstance(raw, list):
        return []
    return list(dict.fromkeys(
        name for name in raw[:MAX_TARGETS]
        if isinstance(name, str) and (
            _TOKEN_RE.fullmatch(name)
            or (name.startswith(".") and CAPTURE_FILE_RE.fullmatch(name))
        )
    ))


def _withdrawal_state(session: Session) -> dict[str, Any]:
    state = _read(session, WITHDRAWAL_KEY)
    if not state:
        if session.get(Setting, WITHDRAWAL_KEY) is not None:
            return {"inventory_incomplete": True, "state_invalid": True}
        return state
    raw = state.get("targets")
    consent_id = state.get("consent_id")
    if (not isinstance(raw, list) or len(raw) > MAX_TARGETS
            or len(_targets(state)) != len(raw)
            or not isinstance(consent_id, str) or not _TOKEN_RE.fullmatch(consent_id)
            or _timestamp(state.get("requested_at")) is None):
        # An unrecognized target is never interpreted as a path or silently
        # treated as deleted. A new explicit request can replace damaged state.
        state["state_invalid"] = True
        state["inventory_incomplete"] = True
    return state


def _target_files(group: str) -> list[tuple[str, str]]:
    names = [group] if group.startswith(".") else [f"{group}.enc", f"{group}.json"]
    return [(directory, name) for directory in DIRECTORIES for name in names]


def _file_stat(directory: str, name: str) -> os.stat_result | None:
    path = capture_directory(directory) / name
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or path.resolve().parent != path.parent:
        raise OSError("unsafe capture file")
    return info


def _unlink(directory: str, name: str) -> tuple[str, int]:
    """Never open a file, follow a link, or recurse into another directory."""
    try:
        info = _file_stat(directory, name)
        if info is None:
            return "missing", 0
        path = capture_directory(directory) / name
        # Unlink removes this name, not a symlink's target. Recheck the parent
        # immediately before it; all application-side moves share file_lock.
        path.unlink(missing_ok=True)
        return "deleted", info.st_size
    except OSError:
        return "failed", 0


def _snapshot(state: dict[str, Any], *, work_scan: str | None = None) -> None:
    scans = [inventory(name, work_scan=work_scan) for name in DIRECTORIES]
    groups = list(dict.fromkeys([*_targets(state), *(f.group for scan in scans for f in scan.files)]))
    state["targets"] = groups[:MAX_TARGETS]
    state["inventory_incomplete"] = (
        bool(state.get("state_invalid")) or len(groups) > MAX_TARGETS
        or any(s.scan_truncated or s.unsafe_files for s in scans)
    )
    counts = state.get("target_file_counts", {})
    if not isinstance(counts, dict):
        counts = {}
    observed: dict[str, int] = {}
    for scan in scans:
        for capture in scan.files:
            observed[capture.group] = observed.get(capture.group, 0) + 1
    state["target_file_counts"] = {
        group: max(_nonnegative(counts.get(group)), observed.get(group, 0), 1)
        for group in state["targets"]
    }
    state["remaining_files"] = sum(state["target_file_counts"].values())


@serialized
def request_withdrawal_cleanup(session: Session, consent_id: str) -> None:
    """Persist intent in the same transaction as revocation, before any unlink."""
    previous = _read(session, WITHDRAWAL_KEY)
    state = {
        "consent_id": consent_id, "requested_at": datetime.now(UTC).isoformat(),
        "targets": _targets(previous), "attempts": 0, "last_attempt_at": None,
        "last_deleted_files": 0, "last_failed_files": 0,
    }
    _snapshot(state)
    _write(session, WITHDRAWAL_KEY, state)


@dataclass
class WorkResult:
    deleted_files: int = 0
    deleted_bytes: int = 0
    expired_files: int = 0
    quota_files: int = 0
    failed_files: int = 0
    attempted_files: int = 0
    budget_exhausted: bool = False
    scan_truncated: bool = False
    dead_letter_deleted_bytes: int = 0

    def public(self, now: datetime) -> dict[str, Any]:
        return {
            "last_run_at": now.isoformat(), "deleted_files": self.deleted_files,
            "deleted_bytes": self.deleted_bytes, "expired_files": self.expired_files,
            "quota_files": self.quota_files, "failed_files": self.failed_files,
            "budget_exhausted": self.budget_exhausted, "scan_truncated": self.scan_truncated,
        }


def _retry_withdrawal(session: Session, result: WorkResult, budget: int, now: datetime) -> None:
    state = _withdrawal_state(session)
    if not state:
        return
    latest = consent.latest(session)
    if latest and latest.status == "withdrawn" and latest.consent_id == state.get("consent_id"):
        # Only the same, still-withdrawn epoch permits discovery of late writes.
        # After any new consent grant, only the exact recorded tokens are retried.
        _snapshot(state, work_scan="withdrawal")
    groups = _targets(state)
    retained: list[str] = []
    attempted_groups: list[str] = []
    before_deleted, before_failed = result.deleted_files, result.failed_files
    remaining_files = 0
    cursors = state.get("target_cursors", {})
    if not isinstance(cursors, dict):
        cursors = {}
    next_cursors: dict[str, int] = {}
    counts = state.get("target_file_counts", {})
    if not isinstance(counts, dict):
        counts = {}
    next_counts: dict[str, int] = {}
    checks = 0
    max_checks = min(MAX_TARGET_STAT_CHECKS, max(64, budget * 8))
    for group in groups:
        if checks + 2 > max_checks or result.attempted_files >= budget:
            retained.append(group)
            next_cursors[group] = _nonnegative(cursors.get(group))
            next_counts[group] = max(1, _nonnegative(counts.get(group)))
            remaining_files += next_counts[group]
            result.budget_exhausted = True
            continue
        attempted = False
        remaining = 0
        files = _target_files(group)
        start = _nonnegative(cursors.get(group)) % len(files)
        indexes = list(range(start, len(files))) + list(range(start))
        next_cursor = start
        for index in indexes:
            directory, name = files[index]
            if checks + 2 > max_checks:
                remaining += 1  # Unverified members remain in scope.
                result.budget_exhausted = True
                continue
            checks += 1
            try:
                info = _file_stat(directory, name)
            except OSError:
                # Unsafe/locked targets stay in the durable request.
                info = None
                remaining += 1
                if result.attempted_files < budget:
                    result.failed_files += 1
                    result.attempted_files += 1
                    attempted = True
                    next_cursor = (index + 1) % len(files)
                else:
                    result.budget_exhausted = True
                continue
            if info is None:
                continue
            if result.attempted_files >= budget:
                remaining += 1
                result.budget_exhausted = True
                continue
            attempted = True
            next_cursor = (index + 1) % len(files)
            result.attempted_files += 1
            outcome, size = _unlink(directory, name)
            checks += 1  # _unlink rechecks the owned file before removing it.
            if outcome == "deleted":
                result.deleted_files += 1
                result.deleted_bytes += size
                result.dead_letter_deleted_bytes += size if directory == "pending_dead_letter" else 0
            elif outcome == "failed":
                remaining += 1
                result.failed_files += 1
        remaining_files += remaining
        if remaining:
            (attempted_groups if attempted else retained).append(group)
            next_cursors[group] = next_cursor
            next_counts[group] = remaining
    # Failed and partially processed frames move to the tail. One locked frame
    # cannot consume every subsequent pass while later frames wait untouched.
    state["targets"] = retained + attempted_groups
    state["target_cursors"] = next_cursors
    state["target_file_counts"] = next_counts
    state["remaining_files"] = remaining_files
    state["attempts"] = _nonnegative(state.get("attempts")) + 1
    state["last_attempt_at"] = now.isoformat()
    state["last_deleted_files"] = result.deleted_files - before_deleted
    state["last_failed_files"] = result.failed_files - before_failed
    result.scan_truncated |= bool(state.get("inventory_incomplete"))
    _write(session, WITHDRAWAL_KEY, state)


@serialized
def retry_withdrawal_cleanup(session: Session, *, limit: int | None = None) -> dict[str, int]:
    """Run after the withdrawal transaction commits. Caller commits progress."""
    budget = get_policy(session)["cleanup_batch_files"] if limit is None else limit
    if not 1 <= budget <= 10_000:
        raise ValueError("capture cleanup limit must be between 1 and 10000")
    result = WorkResult()
    _retry_withdrawal(session, result, budget, datetime.now(UTC))
    saved = _read(session, STATUS_KEY)
    if saved and result.dead_letter_deleted_bytes:
        for key in ("quota_seen_bytes", "quota_deletion_debt_bytes"):
            saved[key] = max(0, _nonnegative(saved.get(key)) - result.dead_letter_deleted_bytes)
        _write(session, STATUS_KEY, saved)
    state = _read(session, WITHDRAWAL_KEY)
    # Preserve the original consent response, where failed also means deferred.
    return {"deleted": result.deleted_files, "failed": max(
        result.failed_files, _nonnegative(state.get("remaining_files")),
        int(bool(state.get("inventory_incomplete"))),
    )}


def _dead_letter_cleanup(
    session: Session, result: WorkResult, budget: int, now: datetime, state: dict[str, Any],
) -> None:
    scan = inventory("pending_dead_letter", work_scan="quota")
    result.scan_truncated |= scan.scan_truncated
    result.failed_files += scan.unsafe_files
    policy = get_policy(session)
    if state.get("quota_policy_bytes") != policy["dead_letter_max_bytes"]:
        # A cap change invalidates old overage estimates. A fresh bounded
        # cycle establishes the new total before additional quota eviction.
        state["quota_policy_bytes"] = policy["dead_letter_max_bytes"]
        state["quota_deletion_debt_bytes"] = 0
        state["quota_cycle_id"] = None
    cutoff = (now - timedelta(days=policy["dead_letter_retention_days"])).timestamp()
    total_bytes = sum(f.size for f in scan.files)
    if scan.cycle_id != state.get("quota_cycle_id"):
        # Directory iterators cannot survive a process restart. Throw away an
        # unfinished cycle's partial sum, while preserving a completed cycle's
        # outstanding overage until files are actually removed.
        state["quota_cycle_id"] = scan.cycle_id
        state["quota_seen_bytes"] = 0
    state["quota_seen_bytes"] = _nonnegative(state.get("quota_seen_bytes")) + total_bytes
    state["quota_cycle_complete"] = scan.cycle_complete
    debt = _nonnegative(state.get("quota_deletion_debt_bytes"))
    if scan.cycle_complete:
        # Refresh the estimate instead of retaining stale overage after a
        # separate/manual deletion has already brought the directory below cap.
        debt = max(0, state["quota_seen_bytes"] - policy["dead_letter_max_bytes"])
    by_group: dict[str, list[CaptureFile]] = {}
    for capture in scan.files:
        by_group.setdefault(capture.group, []).append(capture)
    ordered = sorted(by_group, key=lambda group: (max(f.mtime for f in by_group[group]), group))
    cursor = state.get("dead_letter_cursor")
    if cursor in ordered:
        index = ordered.index(cursor) + 1
        ordered = ordered[index:] + ordered[:index]
    for group in ordered:
        files = by_group[group]
        expired = max(f.mtime for f in files) < cutoff
        overage = max(debt - result.dead_letter_deleted_bytes,
                      total_bytes - policy["dead_letter_max_bytes"])
        if not expired and overage <= 0:
            continue
        ordered_files = sorted(files, key=lambda f: f.name)
        file_cursor = state.get("dead_letter_file_cursor")
        names = [f.name for f in ordered_files]
        if file_cursor in names:
            index = names.index(file_cursor) + 1
            ordered_files = ordered_files[index:] + ordered_files[:index]
        for capture in ordered_files:
            if result.attempted_files >= budget:
                result.budget_exhausted = True
                return
            result.attempted_files += 1
            state["dead_letter_cursor"] = group
            state["dead_letter_file_cursor"] = capture.name
            outcome, size = _unlink(capture.directory, capture.name)
            if outcome == "deleted":
                result.deleted_files += 1
                result.deleted_bytes += size
                result.dead_letter_deleted_bytes += size
                result.expired_files += int(expired)
                result.quota_files += int(not expired)
                total_bytes -= size
            elif outcome == "failed":
                result.failed_files += 1


@serialized
def run_cleanup(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """One bounded pass; the caller commits both counters and retry progress."""
    now = now or datetime.now(UTC)
    result = WorkResult()
    state = _read(session, STATUS_KEY)
    budget = get_policy(session)["cleanup_batch_files"]
    run_count = _nonnegative(state.get("run_count"))
    # Alternate priority so locked withdrawal targets cannot starve normal TTL
    # cleanup, including when an administrator selects a one-file budget.
    if run_count % 2:
        _dead_letter_cleanup(session, result, budget, now, state)
        _retry_withdrawal(session, result, budget, now)
    else:
        _retry_withdrawal(session, result, budget, now)
        _dead_letter_cleanup(session, result, budget, now, state)
    state["quota_seen_bytes"] = max(
        0, _nonnegative(state.get("quota_seen_bytes")) - result.dead_letter_deleted_bytes,
    )
    state["quota_deletion_debt_bytes"] = max(
        0, _nonnegative(state.get("quota_deletion_debt_bytes")) - result.dead_letter_deleted_bytes,
    )
    if state.get("quota_cycle_complete"):
        state["quota_deletion_debt_bytes"] = max(
            0, state["quota_seen_bytes"] - get_policy(session)["dead_letter_max_bytes"],
        )
    public = result.public(now)
    _write(session, STATUS_KEY, {
        **state, **public, "run_count": run_count + 1,
    })
    return public


def _nonnegative(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return None


@serialized
def status(session: Session) -> dict[str, Any]:
    """Only allowlisted counters leave this service; never persisted raw state."""
    saved = _read(session, STATUS_KEY)
    state = _withdrawal_state(session)
    remaining_events = session.query(Event).filter(Event.deletion_state == "pending_delete").count()
    remaining_blobs = session.query(EvidenceBlob).filter(
        EvidenceBlob.deletion_state.in_(["pending_delete", "delete_failed"])
    ).count()
    cleanup: dict[str, Any] = {"last_run_at": _timestamp(saved.get("last_run_at"))}
    for key in ("deleted_files", "deleted_bytes", "expired_files", "quota_files", "failed_files"):
        cleanup[key] = _nonnegative(saved.get(key))
    for key in ("budget_exhausted", "scan_truncated"):
        cleanup[key] = saved.get(key) is True
    return {
        "policy": get_policy(session),
        "worker": {
            "enabled": bool(settings_mod.settings.retention_cleanup_enabled),
            "interval_seconds": max(60, int(settings_mod.settings.retention_cleanup_interval_seconds)),
        },
        "pending": inventory("pending").public(),
        "dead_letter": inventory("pending_dead_letter").public(),
        "cleanup": cleanup,
        "withdrawal_cleanup": {
            "pending": bool(_targets(state) or state.get("inventory_incomplete")
                            or (state and (remaining_events or remaining_blobs))),
            "requested_at": _timestamp(state.get("requested_at")),
            "last_attempt_at": _timestamp(state.get("last_attempt_at")),
            "attempts": _nonnegative(state.get("attempts")),
            "remaining_files": _nonnegative(state.get("remaining_files")),
            "remaining_events": remaining_events, "remaining_blobs": remaining_blobs,
            "inventory_incomplete": state.get("inventory_incomplete") is True,
            "last_deleted_files": _nonnegative(state.get("last_deleted_files")),
            "last_failed_files": _nonnegative(state.get("last_failed_files")),
        },
    }


@serialized
def purge_capture_files(*, limit: int = 10_000) -> dict[str, int]:
    """Compatibility helper for an immediate, bounded explicit evidence wipe.

    The consent API uses durable request/retry methods instead. This helper is
    retained for isolated callers and reports over-budget work as incomplete.
    """
    if not 1 <= limit <= 10_000:
        raise ValueError("capture cleanup limit must be between 1 and 10000")
    result = {"deleted": 0, "failed": 0}
    attempted = 0
    for directory in DIRECTORIES:
        scan = inventory(directory)
        result["failed"] += scan.unsafe_files + int(scan.scan_truncated and not scan.unsafe_files)
        for capture in scan.files:
            if attempted >= limit:
                result["failed"] += 1
                continue
            attempted += 1
            outcome, _ = _unlink(directory, capture.name)
            result["deleted"] += int(outcome == "deleted")
            result["failed"] += int(outcome == "failed")
    return result
