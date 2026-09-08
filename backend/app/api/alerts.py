"""Alert review + actions."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import PureWindowsPath

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from ulid import ULID

from app.api.deps import current_user, get_db_dep, require_recent_auth
from app.db.models import Alert, DeviceCommand, Event, RiskResult, User
from app.services import encryption, purge
from app.services.audit import log_action

router = APIRouter(prefix="/alerts", tags=["alerts"])
actions_router = APIRouter(prefix="/actions", tags=["actions"])


class AlertDTO(BaseModel):
    alert_id: str
    risk_id: str
    device_id: str | None
    profile_id: str | None
    severity: str
    status: str
    created_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    action_taken: str | None
    notes: str | None
    # Context so the feed can say *what* happened without a click-through.
    categories: list[str] = []
    summary: str | None = None
    app_name: str | None = None
    # Repeat aggregation: how many identical findings this alert absorbed.
    repeat_count: int = 1
    last_seen_at: datetime | None = None


def _to_dto(a: Alert, risk: RiskResult | None = None, event: Event | None = None) -> AlertDTO:
    return AlertDTO(
        alert_id=a.alert_id,
        risk_id=a.risk_id,
        device_id=a.device_id,
        profile_id=a.profile_id,
        severity=a.severity,
        status=a.status,
        created_at=a.created_at,
        reviewed_by=a.reviewed_by,
        reviewed_at=a.reviewed_at,
        action_taken=a.action_taken,
        notes=a.notes,
        categories=list(risk.categories or []) if risk else [],
        summary=risk.summary if risk else None,
        app_name=event.app_name if event else None,
        repeat_count=a.repeat_count or 1,
        last_seen_at=a.last_seen_at,
    )


class AlertPage(BaseModel):
    items: list[AlertDTO]
    next_cursor: str | None
    open_count: int


@router.get("", response_model=AlertPage)
def list_alerts(
    severity: str | None = None,
    status: str | None = None,
    device_id: str | None = None,
    profile_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    q = db.query(Alert)
    if severity:
        q = q.filter(Alert.severity == severity)
    if status:
        q = q.filter(Alert.status == status)
    if device_id:
        q = q.filter(Alert.device_id == device_id)
    if profile_id:
        q = q.filter(Alert.profile_id == profile_id)
    if cursor:
        anchor = db.get(Alert, cursor)
        if anchor is None:
            raise HTTPException(400, "Invalid alert cursor")
        q = q.filter(or_(
            Alert.created_at < anchor.created_at,
            and_(Alert.created_at == anchor.created_at, Alert.alert_id < anchor.alert_id),
        ))
    rows_with_extra = q.order_by(
        Alert.created_at.desc(), Alert.alert_id.desc()
    ).limit(limit + 1).all()
    rows = rows_with_extra[:limit]
    risk_ids = [a.risk_id for a in rows if a.risk_id]
    risks = {
        r.risk_id: r
        for r in db.query(RiskResult).filter(RiskResult.risk_id.in_(risk_ids)).all()
    } if risk_ids else {}
    event_ids = [r.event_id for r in risks.values() if r.event_id]
    events = {
        e.event_id: e
        for e in db.query(Event).filter(Event.event_id.in_(event_ids)).all()
    } if event_ids else {}
    out = []
    for a in rows:
        risk = risks.get(a.risk_id)
        event = events.get(risk.event_id) if risk else None
        out.append(_to_dto(a, risk, event))
    return AlertPage(
        items=out,
        next_cursor=rows[-1].alert_id if len(rows_with_extra) > limit else None,
        open_count=db.query(Alert).filter(Alert.status == "open").count(),
    )


class AlertDetail(BaseModel):
    alert: AlertDTO
    risk: dict
    event: dict
    redacted_text: str | None
    synthetic: bool = False
    demo_context: dict | None = None


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: str,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found")
    r = db.get(RiskResult, a.risk_id)
    e = db.get(Event, r.event_id) if r else None
    redacted_text = None
    if e and e.redacted_text_enc:
        try:
            redacted_text = encryption.decrypt_text(e.redacted_text_enc)
        except Exception:
            redacted_text = None
    log_action(db, actor=str(user.id), action="alert.view", target=alert_id)
    db.commit()
    return AlertDetail(
        alert=_to_dto(a, r, e),
        risk={
            "risk_id": r.risk_id if r else None,
            "risk_level": r.risk_level if r else None,
            "score": r.score if r else 0,
            "categories": r.categories if r else [],
            "summary": r.summary if r else "",
            "evidence": r.evidence if r else [],
            "recommended_action": r.recommended_action if r else "none",
            "model": r.model if r else None,
            "rules_triggered": r.rules_triggered if r else [],
            "confidence": r.confidence if r else 0.0,
            "prompt_version": r.prompt_version if r else None,
            "rules_version": r.rules_version if r else None,
        },
        event={
            "event_id": e.event_id if e else None,
            "source_type": e.source_type if e else None,
            "app_name": e.app_name if e else None,
            "window_title": e.window_title if e else None,
            "url": e.url if e else None,
            "timestamp": e.timestamp.isoformat() if e else None,
        },
        redacted_text=redacted_text,
        synthetic=bool((e.event_metadata or {}).get("synthetic")) if e else False,
        demo_context={
            key: (e.event_metadata or {}).get(key)
            for key in (
                "scenario_id",
                "demo_version",
                "relationship_context",
                "repeated_behavior",
                "parent_goal",
            )
        } if e and (e.event_metadata or {}).get("synthetic") else None,
    )


class ReviewRequest(BaseModel):
    status: str = Field(pattern="^(reviewed|false_positive|escalated|dismissed)$")
    notes: str | None = Field(default=None, max_length=4096)


@router.post("/{alert_id}/review", response_model=AlertDTO)
def review_alert(
    alert_id: str,
    req: ReviewRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found")
    a.status = req.status
    a.reviewed_by = str(user.id)
    a.reviewed_at = datetime.now(UTC)
    if req.notes is not None:
        a.notes = req.notes
    log_action(
        db, actor=str(user.id), action="alert.review",
        target=alert_id, details={"status": req.status},
    )
    db.commit()
    return _to_dto(a)


class FeedbackRequest(BaseModel):
    feedback_type: str = Field(pattern="^(false_positive|confirmed|too_low|too_high|missed_context)$")
    notes: str | None = Field(default=None, max_length=4096)


@router.post("/{alert_id}/feedback", response_model=AlertDTO)
def record_feedback(
    alert_id: str,
    req: FeedbackRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found")
    r = db.get(RiskResult, a.risk_id)
    note = f"{req.feedback_type}: {req.notes or ''}".strip()
    if r is not None:
        existing = (r.false_positive_notes or "").strip()
        r.false_positive_notes = (existing + "\n" + note).strip() if existing else note
    if req.feedback_type == "false_positive":
        a.status = "false_positive"
        a.reviewed_by = str(user.id)
        a.reviewed_at = datetime.now(UTC)
    log_action(
        db,
        actor=str(user.id),
        action="alert.feedback",
        target=alert_id,
        details={"feedback_type": req.feedback_type},
    )
    db.commit()
    return _to_dto(a)


class ActionRequest(BaseModel):
    action: str = Field(pattern="^(notify|escalate|pause_app|block_app|delete_evidence)$")
    note: str | None = Field(default=None, max_length=4096)


@router.post("/{alert_id}/action", response_model=AlertDTO)
def take_action(
    alert_id: str,
    req: ActionRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found")
    if req.action in {"pause_app", "block_app", "delete_evidence"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "confirmed_action_required",
                "endpoint": f"/api/alerts/{alert_id}/actions",
            },
        )
    risk = db.get(RiskResult, a.risk_id)
    if req.action == "notify":
        from app.services import notifications

        notifications.enqueue(
            db,
            alert=a,
            risk_summary=risk.summary if risk is not None else "",
            immediate=True,
        )
    elif req.action == "escalate":
        a.status = "escalated"
        a.reviewed_by = str(user.id)
        a.reviewed_at = datetime.now(UTC)
    a.action_taken = req.action
    log_action(
        db, actor=str(user.id), action="alert.action",
        target=alert_id, details={"action": req.action, "note": req.note},
    )
    db.commit()
    return _to_dto(a)


_FQDN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)


class ConfirmedActionRequest(BaseModel):
    action: str = Field(
        pattern="^(show_child_prompt|pause_app|block_domain|delete_evidence)$"
    )
    target: str | None = Field(default=None, max_length=1024)
    duration_seconds: int | None = None
    message: str | None = Field(default=None, max_length=500)
    confirmed_preview: str | None = Field(default=None, max_length=2048)


class ActionDTO(BaseModel):
    action_id: str
    alert_id: str | None
    device_id: str
    action: str
    status: str
    preview: str
    expires_at: datetime
    undo_of: str | None = None


def _canonical_executable(value: str | None) -> str:
    raw = (value or "").strip()
    path = PureWindowsPath(raw)
    if not raw or not path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".exe":
        raise HTTPException(422, "pause_app requires an exact absolute .exe path")
    return str(path)


def _canonical_domain(value: str | None) -> str:
    raw = (value or "").strip().rstrip(".").lower()
    if any(mark in raw for mark in ("://", "/", "*", "@")):
        raise HTTPException(422, "block_domain requires one exact FQDN")
    try:
        canonical = raw.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HTTPException(422, "block_domain target is not a valid FQDN") from exc
    if not _FQDN_RE.fullmatch(canonical):
        raise HTTPException(422, "block_domain requires one exact FQDN")
    return canonical


def _action_payload(req: ConfirmedActionRequest) -> tuple[dict, str]:
    if req.action == "pause_app":
        target = _canonical_executable(req.target)
        if req.duration_seconds not in {900, 3600, 86400}:
            raise HTTPException(422, "pause_app duration must be 15 minutes, 1 hour, or 24 hours")
        label = {900: "15 minutes", 3600: "1 hour", 86400: "24 hours"}[req.duration_seconds]
        return {"target": target, "duration_seconds": req.duration_seconds}, f"Pause {target} for {label}"
    if req.action == "block_domain":
        target = _canonical_domain(req.target)
        return {"target": target}, f"Block exactly {target} until you undo this action"
    if req.action == "show_child_prompt":
        message = (req.message or "").strip()
        if not message:
            raise HTTPException(422, "show_child_prompt requires a message")
        return {"message": message}, f"Show this notice on the child's device: {message}"
    return {}, "Permanently delete this alert's stored evidence and safety record"


def _command_dto(command: DeviceCommand) -> ActionDTO:
    return ActionDTO(
        action_id=command.command_id,
        alert_id=command.alert_id,
        device_id=command.device_id,
        action=command.command_type,
        status=command.status,
        preview=command.preview,
        expires_at=command.expires_at,
        undo_of=command.undo_of,
    )


@router.post("/{alert_id}/actions", response_model=ActionDTO)
def create_confirmed_action(
    alert_id: str,
    req: ConfirmedActionRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    if not alert.device_id:
        raise HTTPException(409, "This alert is not linked to a child device")
    payload, preview = _action_payload(req)
    if req.confirmed_preview != preview:
        raise HTTPException(409, {"code": "confirmation_required", "preview": preview})
    now = datetime.now(UTC)
    command = DeviceCommand(
        command_id=str(ULID()),
        device_id=alert.device_id,
        alert_id=alert_id,
        command_type=req.action,
        payload=payload,
        preview=preview,
        status="queued",
        created_by=user.id,
        expires_at=now + timedelta(hours=24),
    )
    db.add(command)
    if req.action == "delete_evidence":
        risk = db.get(RiskResult, alert.risk_id)
        counts = purge.delete_events(db, [risk.event_id] if risk else [])
        command.status = "completed" if counts["events"] else "pending_delete"
        command.completed_at = now if counts["events"] else None
        command.result = counts
    else:
        alert.action_taken = req.action
    log_action(
        db,
        actor=str(user.id),
        action="alert.action.confirmed",
        target=command.command_id,
        details={"alert_id": alert_id, "action": req.action, "preview": preview},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return _command_dto(command)


@actions_router.post("/{action_id}/undo", response_model=ActionDTO)
def undo_action(
    action_id: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    original = db.get(DeviceCommand, action_id)
    if original is None or original.command_type not in {"pause_app", "block_domain"}:
        raise HTTPException(409, "This action cannot be undone")
    if db.query(DeviceCommand).filter(DeviceCommand.undo_of == action_id).first():
        raise HTTPException(409, "This action has already been undone")
    command = DeviceCommand(
        command_id=str(ULID()),
        device_id=original.device_id,
        alert_id=original.alert_id,
        command_type="undo_action",
        payload={"original_action": original.command_type, **(original.payload or {})},
        preview=f"Undo: {original.preview}",
        status="queued",
        created_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
        undo_of=action_id,
    )
    db.add(command)
    log_action(
        db,
        actor=str(user.id),
        action="alert.action.undo",
        target=command.command_id,
        details={"undo_of": action_id},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return _command_dto(command)
