"""Storage usage, encrypted export, and wipe controls."""
from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from ulid import ULID

from app.api.deps import current_user, get_db_dep
from app.db.models import Alert, AuditLog, EvidenceBlob, Event, RiskResult, User
from app.services import encryption
from app.services.audit import log_action
from app.settings import settings

router = APIRouter(prefix="/storage", tags=["storage"])


def _exports_dir() -> Path:
    path = settings.data_dir / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


@router.post("/export")
def export_storage(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    """Full local evidence export.

    The package contains all metadata (JSONL) plus every encrypted evidence
    blob file (`evidence/<blob_id>.enc`, AES-GCM as stored on disk). The zip is
    written to a temporary file, then encrypted in chunks into a `.gnexport`.
    Evidence stays local and decryptable only with this server's master key.
    """
    export_id = str(ULID())
    missing_files: list[str] = []
    dest = _exports_dir() / f"{export_id}.gnexport"
    tmp_dir = _exports_dir() / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_zip = tmp_dir / f"{export_id}.zip"
    included_blob_count = 0
    try:
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            _write_jsonl(zf, "alerts.jsonl", db.query(Alert))
            _write_jsonl(zf, "events.jsonl", db.query(Event))
            _write_jsonl(zf, "risk_results.jsonl", db.query(RiskResult))
            _write_jsonl(zf, "audit_logs.jsonl", db.query(AuditLog))
            _write_json_array(zf, "evidence_manifest.json", db.query(EvidenceBlob))
            for blob in db.query(EvidenceBlob).yield_per(100):
                src = Path(blob.encrypted_path)
                if not src.is_file():
                    missing_files.append(blob.blob_id)
                    continue
                # Stored ciphertext is copied as-is; aad = blob_id, key = master key.
                zf.write(src, arcname=f"evidence/{blob.blob_id}.enc")
                included_blob_count += 1
            manifest = {
                "export_id": export_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "format": "guardiannode-full-export-v3",
                "outer_encryption": "chunked-aes-256-gcm",
                "includes_evidence_blobs": True,
                "evidence_blob_count": included_blob_count,
                "evidence_blobs_missing": missing_files,
                "note": (
                    "evidence/*.enc files are AES-256-GCM ciphertext exactly as stored; "
                    "decryption requires this server's master key (keys/master.key) "
                    "with the blob_id as associated data."
                ),
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        encryption.encrypt_file_to_disk(tmp_zip, dest, aad=export_id.encode("ascii"))
    finally:
        try:
            tmp_zip.unlink(missing_ok=True)
        except OSError:
            pass
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
        details={"path": str(dest), "size_bytes": dest.stat().st_size},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True, "export_id": export_id, "path": str(dest), "size_bytes": dest.stat().st_size}


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
        cutoff = datetime.now(timezone.utc) - timedelta(days=req.older_than_days)
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
