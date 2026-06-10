"""Risk results — list + feedback."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep
from app.db.models import RiskResult, User
from app.services.audit import log_action

router = APIRouter(prefix="/risks", tags=["risks"])


class RiskDTO(BaseModel):
    risk_id: str
    event_id: str
    risk_level: str
    score: int
    categories: list[str]
    summary: str
    model: str | None
    confidence: float
    created_at: datetime


def _to_dto(r: RiskResult) -> RiskDTO:
    return RiskDTO(
        risk_id=r.risk_id,
        event_id=r.event_id,
        risk_level=r.risk_level,
        score=r.score,
        categories=r.categories,
        summary=r.summary,
        model=r.model,
        confidence=r.confidence,
        created_at=r.created_at,
    )


@router.get("", response_model=list[RiskDTO])
def list_risks(
    risk_level: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    q = db.query(RiskResult).order_by(RiskResult.created_at.desc())
    if risk_level:
        q = q.filter(RiskResult.risk_level == risk_level)
    return [_to_dto(r) for r in q.limit(limit).all()]


class FeedbackRequest(BaseModel):
    is_false_positive: bool
    notes: str | None = Field(default=None, max_length=2048)


@router.post("/{risk_id}/feedback")
def feedback(
    risk_id: str,
    req: FeedbackRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    r = db.get(RiskResult, risk_id)
    if r is None:
        raise HTTPException(404, "Risk not found")
    if req.is_false_positive:
        r.false_positive_notes = (r.false_positive_notes or "") + (
            "\n[user]" + (req.notes or "marked FP") if req.notes else "\n[user] marked FP"
        )
    log_action(
        db, actor=str(user.id), action="risk.feedback",
        target=risk_id, details={"is_fp": req.is_false_positive},
    )
    db.commit()
    return {"ok": True}
