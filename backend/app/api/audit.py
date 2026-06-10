"""Audit log browsing for parents."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep
from app.db.models import AuditLog, User

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditDTO(BaseModel):
    id: int
    actor: str
    action: str
    target: str | None
    details: dict
    source_ip: str | None
    created_at: datetime


@router.get("", response_model=list[AuditDTO])
def list_audit(
    action: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    return q.limit(limit).all()
