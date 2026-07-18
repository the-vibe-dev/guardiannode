"""Alert review + actions."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep
from app.db.models import Alert, Event, RiskResult, User
from app.services import encryption
from app.services.audit import log_action

router = APIRouter(prefix="/alerts", tags=["alerts"])


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


@router.get("", response_model=list[AlertDTO])
def list_alerts(
    severity: str | None = None,
    status: str | None = None,
    device_id: str | None = None,
    profile_id: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    q = db.query(Alert).order_by(Alert.created_at.desc())
    if severity:
        q = q.filter(Alert.severity == severity)
    if status:
        q = q.filter(Alert.status == status)
    if device_id:
        q = q.filter(Alert.device_id == device_id)
    if profile_id:
        q = q.filter(Alert.profile_id == profile_id)
    rows = q.limit(limit).all()
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
    return out


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
        # These actions were present in the early schema before an enforcement
        # transport existed.  Never acknowledge an enforcement request that did
        # not actually happen.
        raise HTTPException(
            status_code=501,
            detail=f"Action {req.action!r} is not implemented in this release",
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
