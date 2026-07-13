"""Parent-configurable notification and retention settings."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep, require_recent_auth
from app.db.models import BackupRun, Setting, User
from app.services import encryption, retention
from app.services.audit import log_action
from app.services.notifications import run_test
from app.workers import backup_worker

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_json(session: Session, key: str, default: dict[str, Any]) -> dict[str, Any]:
    row = session.get(Setting, key)
    if not row or not row.value:
        return dict(default)
    try:
        data = json.loads(row.value)
    except Exception:
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def _set_json(session: Session, key: str, value: dict[str, Any]) -> None:
    row = session.get(Setting, key)
    text = json.dumps(value, sort_keys=True)
    if row is None:
        session.add(Setting(key=key, value=text))
    else:
        row.value = text


class NotificationSettings(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    tls_mode: str = Field(default="starttls", pattern="^(starttls|ssl|none)$")
    username: str = Field(default="", max_length=255)
    password: str | None = None
    clear_password: bool = False
    from_address: str = Field(default="", max_length=320)
    to_address: str = Field(default="", max_length=320)
    webhook_url: str = Field(default="", max_length=2048)
    webhook_allow_private: bool = False
    immediate_min_severity: str = Field(default="high", pattern="^(critical|high|medium|low)$")
    daily_digest_enabled: bool = True
    daily_digest_time: str = "08:00"


def _public_notifications(data: dict[str, Any]) -> dict[str, Any]:
    out = {
        "enabled": bool(data.get("enabled", False)),
        "host": data.get("host", ""),
        "port": int(data.get("port", 587) or 587),
        "tls_mode": data.get("tls_mode", "starttls"),
        "username": data.get("username", ""),
        "password": None,
        "password_configured": bool(data.get("password_enc")),
        "from_address": data.get("from_address", ""),
        "to_address": data.get("to_address", ""),
        "webhook_url": data.get("webhook_url", ""),
        "webhook_allow_private": bool(data.get("webhook_allow_private", False)),
        "immediate_min_severity": data.get("immediate_min_severity", "high"),
        "daily_digest_enabled": bool(data.get("daily_digest_enabled", True)),
        "daily_digest_time": data.get("daily_digest_time", "08:00"),
    }
    return out


def _decrypt_password(data: dict[str, Any]) -> str:
    enc = data.get("password_enc")
    if not enc:
        return ""
    try:
        return encryption.decrypt_text(base64.b64decode(enc.encode("ascii")))
    except Exception:
        return ""


@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    return _public_notifications(_get_json(db, "notification_settings", {}))


@router.patch("/notifications")
def update_notifications(
    req: NotificationSettings,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    existing = _get_json(db, "notification_settings", {})
    data = req.model_dump(exclude={"password", "clear_password"})
    password_action = "preserved"
    if req.clear_password:
        password_action = "cleared"
    elif req.password:
        data["password_enc"] = base64.b64encode(
            encryption.encrypt_text(req.password)
        ).decode("ascii")
        password_action = "replaced"
    elif existing.get("password_enc"):
        data["password_enc"] = existing["password_enc"]
    _set_json(db, "notification_settings", data)
    log_action(
        db,
        actor=str(user.id),
        action="settings.notifications.update",
        details={
            "enabled": data["enabled"],
            "host": data["host"],
            "to_address": data["to_address"],
            "password_action": password_action,
        },
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return _public_notifications(data)


@router.post("/notifications/test")
def test_notifications(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    data = _get_json(db, "notification_settings", {})
    cfg = dict(data)
    cfg["password"] = _decrypt_password(data)
    results = run_test(cfg)
    overall_ok = all(r["ok"] for r in results)
    # One audit row per channel so the Audit page shows a per-channel delivery trail.
    for r in results:
        log_action(
            db,
            actor=str(user.id),
            action="settings.notifications.test",
            details={"channel": r["channel"], "result": "ok" if r["ok"] else "error",
                     "detail": r["detail"] if not r["ok"] else None},
            source_ip=request.client.host if request.client else None,
        )
    db.commit()
    # Keep ok/detail for backward compatibility; results carries per-channel outcomes.
    return {"ok": overall_ok, "detail": "; ".join(f"{r['channel']}: {r['detail']}" for r in results),
            "results": results}


class RetentionSettings(BaseModel):
    critical: int = Field(default=90, ge=1, le=3650)
    high: int = Field(default=90, ge=1, le=3650)
    medium: int = Field(default=30, ge=1, le=3650)
    low: int = Field(default=1, ge=0, le=3650)
    none: int = Field(default=0, ge=0, le=3650)
    screenshots_flagged: int = Field(default=30, ge=1, le=3650)
    audit_logs: int = Field(default=180, ge=1, le=3650)


@router.get("/retention")
def get_retention(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    return {**retention.DEFAULT_RETENTION_DAYS, **_get_json(db, "retention_settings", {})}


@router.patch("/retention")
def update_retention(
    req: RetentionSettings,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    data = req.model_dump()
    if data["incremental_evidence"]:
        raise HTTPException(
            status_code=422,
            detail="Incremental evidence chains are not enabled in this release; use complete backups",
        )
    _set_json(db, "retention_settings", data)
    log_action(
        db,
        actor=str(user.id),
        action="settings.retention.update",
        details=data,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return data


@router.post("/retention/run-cleanup")
def run_retention_cleanup(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    data = {**retention.DEFAULT_RETENTION_DAYS, **_get_json(db, "retention_settings", {})}
    result = retention.run_cleanup(db, data)
    log_action(
        db,
        actor=str(user.id),
        action="retention.cleanup",
        details=result,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return result


class BackupSettings(BaseModel):
    enabled: bool = False
    destination: str = Field(min_length=1, max_length=4096)
    recipient_public_key: str = Field(default="", max_length=8192)
    retention_count: int = Field(default=7, ge=1, le=365)
    interval_seconds: int = Field(default=86400, ge=300, le=31_536_000)
    incremental_evidence: bool = False
    hook_argv: list[str] = Field(default_factory=list, max_length=16)


def _backup_public(config: dict[str, Any]) -> dict[str, Any]:
    return {
        **config,
        "recipient_configured": bool(config.get("recipient_public_key")),
    }


@router.get("/backups")
def get_backups(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    config = backup_worker.load_config(db)
    latest = db.query(BackupRun).order_by(BackupRun.started_at.desc()).limit(20).all()
    return {
        "config": _backup_public(config),
        "runs": [
            {
                "backup_id": row.backup_id,
                "status": row.status,
                "destination": row.destination,
                "archive_path": row.archive_path,
                "size_bytes": row.size_bytes,
                "evidence_covered": row.evidence_covered,
                "recoverable_key": row.recoverable_key,
                "error_code": row.error_code,
                "error_detail": row.error_detail,
                "started_at": row.started_at,
                "completed_at": row.completed_at,
                "verified_at": row.verified_at,
                "restore_tested_at": row.restore_tested_at,
            }
            for row in latest
        ],
    }


@router.patch("/backups")
def update_backups(
    req: BackupSettings,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    from cryptography.hazmat.primitives import serialization

    data = req.model_dump()
    if any(not item or len(item) > 1024 for item in data["hook_argv"]):
        raise HTTPException(status_code=422, detail="Backup hook arguments must be 1-1024 characters")
    if data["recipient_public_key"]:
        try:
            key = backup_worker._public_key(data["recipient_public_key"])
            data["recipient_fingerprint"] = hashlib.sha256(key.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )).hexdigest()
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif data["enabled"]:
        raise HTTPException(status_code=422, detail="A recovery public key is required")
    destination = Path(data["destination"]).expanduser()
    if not destination.is_absolute():
        raise HTTPException(status_code=422, detail="Backup destination must be an absolute path")
    data["destination"] = str(destination)
    _set_json(db, "complete_backup_config", data)
    log_action(
        db,
        actor=str(user.id),
        action="settings.backups.update",
        details={
            "enabled": data["enabled"],
            "destination": data["destination"],
            "recipient_fingerprint": data.get("recipient_fingerprint", ""),
            "retention_count": data["retention_count"],
        },
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return _backup_public(data)


@router.post("/backups/run")
def run_complete_backup(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    config = backup_worker.load_config(db)
    if not config.get("enabled"):
        raise HTTPException(status_code=409, detail="Complete backups are not enabled")
    try:
        archive = backup_worker.run_once(config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Complete backup failed: {exc}") from exc
    log_action(
        db, actor=str(user.id), action="backup.run", target=str(archive),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True, "archive": str(archive)}


@router.post("/backups/{backup_id}/restore-tested")
def mark_restore_tested(
    backup_id: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    row = db.get(BackupRun, backup_id)
    if row is None or row.status != "verified":
        raise HTTPException(status_code=404, detail="Verified backup not found")
    row.restore_tested_at = datetime.now(UTC)
    log_action(
        db, actor=str(user.id), action="backup.restore_tested", target=backup_id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True, "restore_tested_at": row.restore_tested_at}
