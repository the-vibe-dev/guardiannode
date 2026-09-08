"""Versioned parental consent, withdrawal, and onboarding status APIs."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ulid import ULID

from app.api.deps import current_user, get_db_dep, require_recent_auth
from app.db.models import ChildProfile, ConsentRecord, Device, Event, Setting, User
from app.services import consent, purge
from app.services.audit import log_action

router = APIRouter(tags=["consent"])


class ConsentChoices(BaseModel):
    screenshots: bool
    apps_and_urls: bool
    retention: bool
    notifications: bool
    external_ai: bool = False
    child_notice_acknowledged: bool


class ConsentGrantRequest(BaseModel):
    notice_version: str
    choices: ConsentChoices


class ConsentWithdrawalRequest(BaseModel):
    evidence_disposition: str = "retain"  # retain | delete


def _public(row: ConsentRecord | None) -> dict:
    return {
        "notice_version": consent.NOTICE_VERSION,
        "active": bool(
            row and row.status == "granted" and row.notice_version == consent.NOTICE_VERSION
        ),
        "record": None if row is None else {
            "consent_id": row.consent_id,
            "notice_version": row.notice_version,
            "status": row.status,
            "choices": row.choices,
            "created_at": row.created_at,
        },
    }


@router.get("/consent")
def consent_status(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    return _public(consent.latest(db))


@router.post("/consent")
def grant_consent(
    req: ConsentGrantRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    if req.notice_version != consent.NOTICE_VERSION:
        raise HTTPException(409, "The privacy notice has changed; review the current version")
    choices = req.choices.model_dump()
    if not choices["child_notice_acknowledged"]:
        raise HTTPException(422, "The child-facing monitoring notice must be acknowledged")
    previous = consent.latest(db)
    row = ConsentRecord(
        consent_id=str(ULID()),
        user_id=user.id,
        notice_version=req.notice_version,
        status="granted",
        choices=choices,
        supersedes_id=previous.consent_id if previous else None,
    )
    db.add(row)
    log_action(
        db,
        actor=str(user.id),
        action="consent.grant",
        target=row.consent_id,
        details={"notice_version": req.notice_version, "choices": choices},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return _public(row)


@router.post("/consent/withdraw")
def withdraw_consent(
    req: ConsentWithdrawalRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    if req.evidence_disposition not in {"retain", "delete"}:
        raise HTTPException(422, "evidence_disposition must be retain or delete")
    previous = consent.latest(db)
    row = ConsentRecord(
        consent_id=str(ULID()),
        user_id=user.id,
        notice_version=consent.NOTICE_VERSION,
        status="withdrawn",
        choices={"evidence_disposition": req.evidence_disposition},
        supersedes_id=previous.consent_id if previous else None,
    )
    db.add(row)
    for device in db.query(Device).all():
        device.paired = False
        device.token_hash = None
        device.status = "consent_withdrawn"
    deletion = None
    if req.evidence_disposition == "delete":
        deletion = purge.delete_events(db, [item[0] for item in db.query(Event.event_id).all()])
    log_action(
        db,
        actor=str(user.id),
        action="consent.withdraw",
        target=row.consent_id,
        details={"evidence_disposition": req.evidence_disposition, "deletion": deletion},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {**_public(row), "deletion": deletion}


@router.get("/onboarding/status")
def onboarding_status(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    active = consent.monitoring_allowed(db)
    steps = [
        {"id": "account", "complete": db.query(User).count() > 0},
        {"id": "timezone", "complete": db.get(Setting, "family_timezone") is not None},
        {"id": "child", "complete": db.query(ChildProfile).count() > 0},
        {"id": "notice", "complete": active},
        {"id": "privacy_choices", "complete": active},
        {"id": "pairing", "complete": db.query(Device).filter(Device.paired.is_(True)).count() > 0},
        {"id": "self_test", "complete": db.query(Device).filter(Device.last_seen.isnot(None)).count() > 0},
        {
            "id": "recovery",
            "complete": db.get(Setting, "recovery_acknowledged_at") is not None,
        },
    ]
    return {
        "complete": all(step["complete"] for step in steps),
        "current_step": next((step["id"] for step in steps if not step["complete"]), None),
        "steps": steps,
        "checked_at": datetime.now(UTC),
    }
