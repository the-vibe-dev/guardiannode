"""Storage usage, encrypted export, and wipe controls."""
from __future__ import annotations

import os
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from ulid import ULID

from app import settings as settings_mod
from app.api.deps import current_user, get_db_dep, parent_user, require_recent_auth
from app.archive.format import ArchiveError, create_archive
from app.db.models import Alert, Event, EvidenceBlob, RiskResult, User
from app.services import capture_queue, purge
from app.services.audit import log_action

router = APIRouter(prefix="/storage", tags=["storage"])

_MAX_EXPORTS = 5
_MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024
_MIN_FREE_BYTES = 1024 * 1024 * 1024
_export_lock = threading.Lock()


class CaptureQueuePolicy(BaseModel):
    dead_letter_retention_days: int = Field(default=7, ge=1, le=90)
    dead_letter_max_bytes: int = Field(default=268435456, ge=1048576, le=4294967296)
    cleanup_batch_files: int = Field(default=256, ge=1, le=1000)


class CaptureQueuePolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dead_letter_retention_days: int | None = Field(default=None, ge=1, le=90)
    dead_letter_max_bytes: int | None = Field(default=None, ge=1048576, le=4294967296)
    cleanup_batch_files: int | None = Field(default=None, ge=1, le=1000)


class CaptureQueueInventory(BaseModel):
    files: int
    frames: int
    bytes: int
    oldest_at: datetime | None
    orphan_files: int
    unsafe_files: int
    scan_truncated: bool


class CaptureQueueWorker(BaseModel):
    enabled: bool
    interval_seconds: int


class CaptureQueueCleanup(BaseModel):
    last_run_at: datetime | None
    deleted_files: int
    deleted_bytes: int
    expired_files: int
    quota_files: int
    failed_files: int
    budget_exhausted: bool
    scan_truncated: bool


class CaptureQueueWithdrawal(BaseModel):
    pending: bool
    requested_at: datetime | None
    last_attempt_at: datetime | None
    attempts: int
    remaining_files: int
    remaining_events: int
    remaining_blobs: int
    inventory_incomplete: bool
    last_deleted_files: int
    last_failed_files: int


class CaptureQueueStatus(BaseModel):
    policy: CaptureQueuePolicy
    worker: CaptureQueueWorker
    pending: CaptureQueueInventory
    dead_letter: CaptureQueueInventory
    cleanup: CaptureQueueCleanup
    withdrawal_cleanup: CaptureQueueWithdrawal


@router.get("/capture-queue", response_model=CaptureQueueStatus)
def get_capture_queue(
    db: Session = Depends(get_db_dep),
    _: User = Depends(parent_user),
):
    return capture_queue.status(db)


@router.patch("/capture-queue", response_model=CaptureQueueStatus)
def update_capture_queue(
    req: CaptureQueuePolicyPatch,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
    _: None = Depends(require_recent_auth),
):
    changes = req.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(422, "Provide at least one non-null capture cleanup policy field")
    policy = capture_queue.set_policy(db, changes)
    log_action(
        db, actor=str(user.id), action="storage.capture_queue.policy", details=policy,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return capture_queue.status(db)


@router.post("/capture-queue/cleanup", response_model=CaptureQueueStatus)
@capture_queue.serialized
def clean_capture_queue(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
    _: None = Depends(require_recent_auth),
):
    retained = purge.retry_pending_deletions(db)
    result = capture_queue.run_cleanup(db)
    log_action(
        db, actor=str(user.id), action="storage.capture_queue.cleanup",
        details={**result, "retained_events": retained["events"], "retained_blobs": retained["blobs"]},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return capture_queue.status(db)


def _exports_dir() -> Path:
    path = settings_mod.settings.data_dir / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def _cleanup_abandoned_exports() -> None:
    root = _exports_dir()
    for pattern in ("*.tmp", "*.partial", "*.partial.*", ".tmp/*.zip"):
        for path in root.glob(pattern):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass


def _export_path(export_id: str) -> Path:
    if not export_id or not all(c.isalnum() for c in export_id):
        raise HTTPException(status_code=400, detail="Invalid export id")
    root = _exports_dir().resolve()
    matches = [
        path for suffix in (".gna", ".gnexport")
        if (path := (root / f"{export_id}{suffix}").resolve(strict=False)).parent == root
        and path.is_file() and not path.is_symlink()
    ]
    if len(matches) != 1:
        raise HTTPException(status_code=404, detail="Export not found")
    return matches[0]


def _final_export_path(export_id: str) -> Path:
    root = _exports_dir().resolve()
    path = (root / f"{export_id}.gna").resolve(strict=False)
    if path.parent != root:
        raise HTTPException(status_code=400, detail="Invalid export id")
    return path


def _fsync_path(path: Path) -> None:
    flags = os.O_RDWR if os.name == "nt" else os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            if os.name != "nt":
                raise
    finally:
        os.close(fd)


def _export_files() -> list[Path]:
    root = _exports_dir()
    return [
        p for pattern in ("*.gna", "*.gnexport") for p in root.glob(pattern)
        if p.is_file() and not p.is_symlink()
    ]


def _ensure_export_capacity() -> None:
    exports = _export_files()
    if len(exports) >= _MAX_EXPORTS:
        raise HTTPException(409, f"Export limit reached ({_MAX_EXPORTS}); delete an old export first")
    total = sum(p.stat().st_size for p in exports)
    if total >= _MAX_EXPORT_BYTES:
        raise HTTPException(409, "Export storage quota reached; delete an old export first")
    if shutil.disk_usage(_exports_dir()).free < _MIN_FREE_BYTES:
        raise HTTPException(507, "Not enough free disk space for export")


class ExportDTO(BaseModel):
    export_id: str
    filename: str
    size_bytes: int
    created_at: datetime
    download_url: str


@router.get("")
def storage_overview(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    blob_bytes = db.query(func.coalesce(func.sum(EvidenceBlob.size_bytes), 0)).scalar() or 0
    export_bytes = 0
    if _exports_dir().exists():
        export_bytes = sum(p.stat().st_size for p in _export_files())
    return {
        "alerts": db.query(func.count(Alert.alert_id)).scalar() or 0,
        "events": db.query(func.count(Event.event_id)).scalar() or 0,
        "risk_results": db.query(func.count(RiskResult.risk_id)).scalar() or 0,
        "evidence_blobs": db.query(func.count(EvidenceBlob.blob_id)).scalar() or 0,
        "evidence_bytes": int(blob_bytes),
        "export_bytes": int(export_bytes),
    }


@router.get("/exports", response_model=list[ExportDTO])
def list_exports(_: User = Depends(current_user)):
    _cleanup_abandoned_exports()
    exports: list[ExportDTO] = []
    for path in sorted(_export_files(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file() or path.is_symlink():
            continue
        export_id = path.stem
        stat = path.stat()
        exports.append(
            ExportDTO(
                export_id=export_id,
                filename=path.name,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                download_url=f"/api/storage/exports/{export_id}/download",
            )
        )
    return exports


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    path = _export_path(export_id)
    log_action(
        db,
        actor=str(user.id),
        action="storage.export.download",
        target=export_id,
        details={"size_bytes": path.stat().st_size},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    response = FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.delete("/exports/{export_id}")
def delete_export(
    export_id: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    path = _export_path(export_id)
    size_bytes = path.stat().st_size
    try:
        path.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete export: {e}") from e
    log_action(
        db,
        actor=str(user.id),
        action="storage.export.delete",
        target=export_id,
        details={"size_bytes": size_bytes},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True}


@router.post("/export")
def export_storage(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    """Create a complete, same-instance GuardianNode Archive v1 snapshot."""
    if not _export_lock.acquire(blocking=False):
        raise HTTPException(409, "Another export is already running")
    try:
        _cleanup_abandoned_exports()
        _ensure_export_capacity()
        export_id = str(ULID())
        dest = _final_export_path(export_id)
        try:
            create_archive(
                dest,
                data_dir=settings_mod.settings.data_dir,
                db_url=settings_mod.settings.db_url_resolved,
                mode="instance_snapshot",
            )
        except ArchiveError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        _export_lock.release()
    if os.name != "nt":
        try:
            os.chmod(dest, 0o600)
        except OSError:
            pass
    log_action(
        db,
        actor=str(user.id),
        action="storage.export",
        target=export_id,
        details={"size_bytes": dest.stat().st_size, "format": "guardiannode-archive-v2"},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "ok": True,
        "export_id": export_id,
        "download_url": f"/api/storage/exports/{export_id}/download",
        "size_bytes": dest.stat().st_size,
    }


class WipeRequest(BaseModel):
    screenshots: bool = False
    low_severity_events: bool = False
    older_than_days: int | None = Field(default=None, ge=1, le=3650)


@router.post("/wipe")
def wipe_storage(
    req: WipeRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    from app.services import purge

    deleted = {"blobs": 0, "low_alerts": 0, "low_risk_results": 0, "low_events": 0, "old_events": 0}
    if req.screenshots:
        for blob in db.query(EvidenceBlob).filter(EvidenceBlob.kind == "screenshot").all():
            if purge.delete_blob(db, blob):
                deleted["blobs"] += 1
        for event in db.query(Event).filter(Event.screenshot_blob_id.isnot(None)).all():
            event.screenshot_blob_id = None

    if req.low_severity_events:
        # Wipe the whole low-severity record chain (event → risk → alert), not
        # just the alert rows, so nothing is stranded.
        low_event_ids = [
            r[0]
            for r in db.query(RiskResult.event_id)
            .filter(RiskResult.risk_level.in_(["low", "none"]))
            .all()
        ]
        counts = purge.delete_events(db, low_event_ids)
        deleted["low_alerts"] = counts["alerts"]
        deleted["low_risk_results"] = counts["risk_results"]
        deleted["low_events"] = counts["events"]
        deleted["blobs"] += counts["blobs"]

    if req.older_than_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=req.older_than_days)
        old_ids = [r[0] for r in db.query(Event.event_id).filter(Event.timestamp < cutoff).all()]
        counts = purge.delete_events(db, old_ids)
        deleted["old_events"] = counts["events"]
        deleted["blobs"] += counts["blobs"]

    log_action(
        db,
        actor=str(user.id),
        action="storage.wipe",
        details={**deleted, **req.model_dump()},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True, "deleted": deleted}
