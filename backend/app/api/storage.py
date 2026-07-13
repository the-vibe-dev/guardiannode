"""Storage usage, encrypted export, and wipe controls."""
from __future__ import annotations

import json
import os
import shutil
import threading
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from ulid import ULID

from app import settings as settings_mod
from app.api.deps import current_user, get_db_dep, require_recent_auth
from app.db.migrations import schema_revisions
from app.db.models import Alert, AuditLog, Event, EvidenceBlob, RiskResult, User
from app.db.session import get_engine
from app.services import encryption
from app.services.audit import log_action
from app.services.evidence_paths import UnsafeEvidencePathError, resolve_stored_evidence_path

router = APIRouter(prefix="/storage", tags=["storage"])

_MAX_EXPORTS = 5
_MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024
_MIN_FREE_BYTES = 1024 * 1024 * 1024
_export_lock = threading.Lock()


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
    for pattern in ("*.tmp", "*.partial", ".tmp/*.zip"):
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
    path = (root / f"{export_id}.gnexport").resolve(strict=False)
    if path.parent != root:
        raise HTTPException(status_code=400, detail="Invalid export id")
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    return path


def _final_export_path(export_id: str) -> Path:
    root = _exports_dir().resolve()
    path = (root / f"{export_id}.gnexport").resolve(strict=False)
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
    return [p for p in root.glob("*.gnexport") if p.is_file() and not p.is_symlink()]


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
        export_bytes = sum(p.stat().st_size for p in _exports_dir().glob("*.gnexport") if p.is_file())
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


def _row_dict(row) -> dict:
    from sqlalchemy import inspect as sa_inspect

    data = {}
    # Iterate ORM attributes, not raw columns: the events table maps the
    # "metadata" column to the event_metadata attribute, and a plain
    # getattr(row, "metadata") would return SQLAlchemy's MetaData object.
    for attr in sa_inspect(row).mapper.column_attrs:
        value = getattr(row, attr.key)
        col_name = attr.columns[0].name
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, bytes):
            value = f"<encrypted:{len(value)} bytes>"
        data[col_name] = value
    return data


def _evidence_manifest(row: EvidenceBlob) -> dict:
    return {
        "blob_id": row.blob_id,
        "event_id": row.event_id,
        "kind": row.kind,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "sha256_plain": row.sha256_plain,
        "key_version": row.key_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _write_jsonl(zf: zipfile.ZipFile, name: str, rows) -> None:
    with zf.open(name, "w") as out:
        for row in rows.yield_per(500):
            out.write(json.dumps(_row_dict(row), separators=(",", ":")).encode("utf-8"))
            out.write(b"\n")


def _write_json_array(zf: zipfile.ZipFile, name: str, rows) -> None:
    first = True
    with zf.open(name, "w") as out:
        out.write(b"[\n")
        for row in rows.yield_per(500):
            if not first:
                out.write(b",\n")
            out.write(json.dumps(_row_dict(row), separators=(",", ":")).encode("utf-8"))
            first = False
        out.write(b"\n]\n")


def _write_evidence_manifest(zf: zipfile.ZipFile, rows) -> None:
    first = True
    with zf.open("evidence_manifest.json", "w") as out:
        out.write(b"[\n")
        for row in rows.yield_per(500):
            if not first:
                out.write(b",\n")
            out.write(json.dumps(_evidence_manifest(row), separators=(",", ":")).encode("utf-8"))
            first = False
        out.write(b"\n]\n")


@router.post("/export")
def export_storage(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    """Full local evidence export.

    The package contains all metadata (JSONL) plus every encrypted evidence
    blob file (`evidence/<blob_id>.enc`, AES-GCM as stored on disk). The zip is
    written to a temporary file, then encrypted in chunks into a `.gnexport`.
    Evidence stays local and decryptable only with this server's master key.
    """
    if not _export_lock.acquire(blocking=False):
        raise HTTPException(409, "Another export is already running")
    try:
        _cleanup_abandoned_exports()
        _ensure_export_capacity()
        export_id = str(ULID())
        missing_files: list[str] = []
        dest = _final_export_path(export_id)
        partial = dest.with_suffix(dest.suffix + ".partial")
        tmp_dir = _exports_dir() / ".tmp"
        _ensure_private_dir(tmp_dir)
        tmp_zip = tmp_dir / f"{export_id}.zip"
        included_blob_count = 0
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                _write_jsonl(zf, "alerts.jsonl", db.query(Alert))
                _write_jsonl(zf, "events.jsonl", db.query(Event))
                _write_jsonl(zf, "risk_results.jsonl", db.query(RiskResult))
                _write_jsonl(zf, "audit_logs.jsonl", db.query(AuditLog))
                _write_evidence_manifest(zf, db.query(EvidenceBlob))
                for blob in db.query(EvidenceBlob).yield_per(100):
                    try:
                        src = resolve_stored_evidence_path(blob.encrypted_path)
                    except (FileNotFoundError, UnsafeEvidencePathError):
                        missing_files.append(blob.blob_id)
                        continue
                    # Stored ciphertext is copied as-is; aad = blob_id, key = master key.
                    zf.write(src, arcname=f"evidence/{blob.blob_id}.enc")
                    included_blob_count += 1
                manifest = {
                    "export_id": export_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "format": "guardiannode-full-export-v3",
                    "schema_revision": schema_revisions(get_engine())[0],
                    "outer_encryption": "chunked-aes-256-gcm",
                    "includes_evidence_blobs": True,
                    "evidence_blob_count": included_blob_count,
                    "evidence_blobs_missing": missing_files,
                    "note": (
                        "evidence/*.enc files are AES-256-GCM ciphertext exactly as stored; "
                        "decryption requires this backend's master key, which may be "
                        "DPAPI-wrapped on Windows or restored from a portable key backup, "
                        "with the blob_id as associated data. The dashboard recovery code "
                        "does not decrypt evidence."
                    ),
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            _fsync_path(tmp_zip)
            encryption.encrypt_file_to_disk(tmp_zip, partial, aad=export_id.encode("ascii"))
            _fsync_path(partial)
            os.replace(partial, dest)
            _fsync_path(dest.parent)
        finally:
            try:
                tmp_zip.unlink(missing_ok=True)
            finally:
                partial.unlink(missing_ok=True)
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
        details={"size_bytes": dest.stat().st_size},
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
            purge.delete_blob(db, blob)
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
