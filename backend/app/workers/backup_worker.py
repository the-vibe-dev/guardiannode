"""Scheduled complete, encrypted, verified GuardianNode backups."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
from sqlalchemy.orm import Session
from ulid import ULID

from app import settings as settings_mod
from app.archive.format import create_archive, verify_archive
from app.db.maintenance import sqlite_path_from_url
from app.db.models import BackupRun, Setting
from app.db.session import get_sessionmaker
from app.services import encryption

log = logging.getLogger(__name__)
_lock = threading.Lock()
_CONFIG_KEY = "complete_backup_config"
_MIN_HEADROOM = 256 * 1024 * 1024


def default_config() -> dict[str, Any]:
    settings = settings_mod.settings
    return {
        "enabled": False,
        "destination": str(settings.backups_dir),
        "recipient_public_key": "",
        "recipient_fingerprint": "",
        "retention_count": max(1, int(settings.database_backup_keep)),
        "interval_seconds": max(300, int(settings.database_backup_interval_seconds)),
        "incremental_evidence": False,
        "hook_argv": [],
    }


def load_config(db: Session | None = None) -> dict[str, Any]:
    own = db is None
    session = db or get_sessionmaker()()
    try:
        row = session.get(Setting, _CONFIG_KEY)
        configured = json.loads(row.value) if row and row.value else {}
        return {**default_config(), **configured}
    finally:
        if own:
            session.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _estimated_bytes() -> int:
    settings = settings_mod.settings
    database = sqlite_path_from_url(settings.db_url_resolved)
    total = database.stat().st_size if database.is_file() else 0
    if settings.evidence_dir.exists():
        total += sum(path.stat().st_size for path in settings.evidence_dir.rglob("*") if path.is_file())
    return total


def _public_key(pem: str) -> X25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode("ascii"))
    if not isinstance(key, X25519PublicKey):
        raise ValueError("backup recipient must be an X25519 public key")
    return key


def _record_started(destination: Path) -> str:
    backup_id = str(ULID())
    with get_sessionmaker()() as db:
        db.add(BackupRun(
            backup_id=backup_id,
            backup_type="complete",
            status="running",
            destination=str(destination),
        ))
        db.commit()
    return backup_id


def _record_finished(backup_id: str, **values: Any) -> None:
    with get_sessionmaker()() as db:
        row = db.get(BackupRun, backup_id)
        if row is None:
            return
        for name, value in values.items():
            setattr(row, name, value)
        row.completed_at = datetime.now(UTC)
        db.commit()


def _prune(destination: Path, keep: int) -> None:
    archives = sorted(
        destination.glob("complete-*.gna"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for stale in archives[max(1, keep):]:
        stale.unlink(missing_ok=True)


def run_once(config: dict[str, Any] | None = None) -> Path | None:
    cfg = config or load_config()
    if not cfg.get("enabled"):
        return None
    if not _lock.acquire(blocking=False):
        raise RuntimeError("another complete backup is already running")
    destination = Path(str(cfg["destination"])).expanduser()
    backup_id = ""
    try:
        if not cfg.get("recipient_public_key"):
            raise RuntimeError("backup recovery public key is not configured")
        destination.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(destination).free < _estimated_bytes() + _MIN_HEADROOM:
            raise RuntimeError("backup destination does not have enough free space")
        backup_id = _record_started(destination)
        archive = destination / (
            f"complete-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{backup_id}.gna"
        )
        create_archive(
            archive,
            data_dir=settings_mod.settings.data_dir,
            db_url=settings_mod.settings.db_url_resolved,
            mode="portable",
            recipient_key=_public_key(str(cfg["recipient_public_key"])),
            include_instance_key_slot=True,
        )
        verified = verify_archive(archive, master_key=encryption.get_master_key())
        if not verified["manifest"]["evidence"]["covered"]:
            raise RuntimeError("backup verification reported incomplete evidence coverage")
        hook = cfg.get("hook_argv") or []
        if hook:
            if not isinstance(hook, list) or not all(isinstance(item, str) for item in hook):
                raise RuntimeError("backup hook must be an argument list")
            subprocess.run([*hook, str(archive)], check=True, timeout=300)
        now = datetime.now(UTC)
        _record_finished(
            backup_id,
            status="verified",
            archive_path=str(archive),
            size_bytes=archive.stat().st_size,
            archive_sha256=_sha256(archive),
            evidence_covered=True,
            recoverable_key=True,
            verified_at=now,
        )
        _prune(destination, int(cfg.get("retention_count", 7)))
        log.info("complete verified backup completed: %s", archive)
        return archive
    except Exception as exc:
        if backup_id:
            _record_finished(
                backup_id,
                status="failed",
                error_code=type(exc).__name__,
                error_detail=str(exc)[:2048],
            )
        log.warning("complete backup failed: %s", exc)
        raise
    finally:
        _lock.release()


async def loop() -> None:
    while True:
        cfg = load_config()
        interval = max(300, int(cfg.get("interval_seconds", 86400)))
        try:
            await asyncio.to_thread(run_once, cfg)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)
