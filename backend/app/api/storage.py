"""Storage usage, encrypted export, and wipe controls."""
from __future__ import annotations

import io
import json
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


def _rows(rows) -> list[dict]:
    out = []
    for row in rows:
        data = {}
        for col in row.__table__.columns:
            value = getattr(row, col.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, bytes):
                value = f"<encrypted:{len(value)} bytes>"
            data[col.name] = value
        out.append(data)
    return out


@router.post("/export")
def export_storage(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    export_id = str(ULID())
    manifest = {
        "export_id": export_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "guardiannode-jsonl-zip-aesgcm-v1",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("alerts.json", "\n".join(json.dumps(r) for r in _rows(db.query(Alert).all())))
        zf.writestr("events.json", "\n".join(json.dumps(r) for r in _rows(db.query(Event).all())))
        zf.writestr("risk_results.json", "\n".join(json.dumps(r) for r in _rows(db.query(RiskResult).all())))
        zf.writestr("audit_logs.json", "\n".join(json.dumps(r) for r in _rows(db.query(AuditLog).all())))
        zf.writestr("evidence_manifest.json", json.dumps(_rows(db.query(EvidenceBlob).all()), indent=2))
    dest = _exports_dir() / f"{export_id}.gnexport"
    encryption.encrypt_blob_to_disk(buf.getvalue(), dest, aad=export_id.encode("ascii"))
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
    deleted = {"blobs": 0, "low_alerts": 0, "old_events": 0}
    if req.screenshots:
        for blob in db.query(EvidenceBlob).filter(EvidenceBlob.kind == "screenshot").all():
            try:
                Path(blob.encrypted_path).unlink(missing_ok=True)
            except Exception:
                pass
            db.delete(blob)
            deleted["blobs"] += 1
        for event in db.query(Event).filter(Event.screenshot_blob_id.isnot(None)).all():
            event.screenshot_blob_id = None

    if req.low_severity_events:
        q = db.query(Alert).filter(Alert.severity == "low")
        deleted["low_alerts"] = q.delete(synchronize_session=False)

    if req.older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=req.older_than_days)
        q = db.query(Event).filter(Event.timestamp < cutoff)
        deleted["old_events"] = q.delete(synchronize_session=False)

    log_action(
        db,
        actor=str(user.id),
        action="storage.wipe",
        details={**deleted, **req.model_dump()},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True, "deleted": deleted}
