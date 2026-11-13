"""Audit log browsing for parents."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_db_dep, parent_user
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


class AuditPageDTO(BaseModel):
    items: list[AuditDTO]
    next_cursor: str | None
    total: int


def _utc(value: datetime) -> datetime:
    # SQLite returns naive values even for timezone-aware DateTime columns.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _cursor(row: AuditLog, fingerprint: str) -> str:
    payload = json.dumps({
        "v": 1, "time": _utc(row.created_at).isoformat(),
        "id": row.id, "filters": fingerprint,
    }, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str, fingerprint: str) -> tuple[datetime, int]:
    try:
        if len(value) > 1024:
            raise ValueError("cursor too long")
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"v", "time", "id", "filters"}:
            raise ValueError("invalid cursor shape")
        if type(payload["v"]) is not int or payload["v"] != 1 or payload["filters"] != fingerprint:
            raise ValueError("cursor belongs to different filters")
        row_id = payload["id"]
        if type(row_id) is not int or not 0 < row_id <= 2**63 - 1:
            raise ValueError("invalid audit ID")
        if not isinstance(payload["time"], str):
            raise ValueError("invalid timestamp")
        timestamp = datetime.fromisoformat(payload["time"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp requires timezone")
        return _utc(timestamp), row_id
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        raise HTTPException(status_code=400, detail="Invalid audit cursor for these filters") from exc


@router.get("/page", response_model=AuditPageDTO)
def page_audit(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    action: str | None = Query(default=None, max_length=128),
    actor: str | None = Query(default=None, max_length=255),
    q: str | None = Query(default=None, max_length=200),
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db_dep),
    _: User = Depends(parent_user),
):
    """Browse retained history with stable keyset pagination and metadata search.

    The lower time bound is inclusive and the upper bound is exclusive. Search
    deliberately excludes event details, which may contain sensitive evidence.
    """
    for name, value in (("since", since), ("until", until)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(status_code=422, detail=f"{name} must include a timezone")
    since = _utc(since) if since is not None else None
    until = _utc(until) if until is not None else None
    if since is not None and until is not None and since >= until:
        raise HTTPException(status_code=422, detail="since must be earlier than until")
    action, actor, search = action or None, actor or None, (q or "").strip()
    fingerprint = hashlib.sha256(json.dumps({
        "action": action, "actor": actor, "q": search,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if search:
        query = query.filter(or_(*(
            field.icontains(search, autoescape=True)
            for field in (AuditLog.actor, AuditLog.action, AuditLog.target, AuditLog.source_ip)
        )))
    if since is not None:
        query = query.filter(AuditLog.created_at >= since)
    if until is not None:
        query = query.filter(AuditLog.created_at < until)
    total = query.count()
    if cursor is not None:
        timestamp, row_id = _decode_cursor(cursor, fingerprint)
        query = query.filter(or_(
            AuditLog.created_at < timestamp,
            (AuditLog.created_at == timestamp) & (AuditLog.id < row_id),
        ))
    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1).all()
    page = rows[:limit]
    return AuditPageDTO(
        items=[AuditDTO.model_validate(row, from_attributes=True).model_copy(
            update={"created_at": _utc(row.created_at)}
        ) for row in page],
        next_cursor=_cursor(page[-1], fingerprint) if len(rows) > limit else None,
        total=total,
    )


@router.get("", response_model=list[AuditDTO])
def list_audit(
    action: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_dep),
    _: User = Depends(parent_user),
):
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    return q.limit(limit).all()
