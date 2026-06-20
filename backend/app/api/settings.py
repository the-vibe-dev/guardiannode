"""Parent-configurable notification and retention settings."""
from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep
from app.db.models import Setting, User
from app.services import encryption, retention
from app.services.audit import log_action
from app.services.notifications import run_test

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
    data = req.model_dump(exclude={"password"})
    if req.password is not None:
        if req.password:
            data["password_enc"] = base64.b64encode(
                encryption.encrypt_text(req.password)
            ).decode("ascii")
    elif existing.get("password_enc"):
        data["password_enc"] = existing["password_enc"]
    _set_json(db, "notification_settings", data)
    log_action(
        db,
        actor=str(user.id),
        action="settings.notifications.update",
        details={"enabled": data["enabled"], "host": data["host"], "to_address": data["to_address"]},
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
