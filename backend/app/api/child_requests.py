"""Read-only legacy exception history; new requests and decisions are retired."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.deps import current_device, get_db_dep, parent_user
from app.db.models import ChildRequest, Device, User

router = APIRouter(prefix="/child-requests", tags=["child-requests"])


class ChildRequestCreate(BaseModel):
    request_type: str = Field(pattern="^(more_time|site_exception|app_exception|other)$")
    target: str | None = Field(default=None, max_length=1024)
    reason: str | None = Field(default=None, max_length=4096)
    profile_id: str | None = None


class ChildRequestDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    device_id: str | None
    profile_id: str | None
    request_type: str
    target: str | None
    reason: str | None
    status: str
    response_note: str | None
    created_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    expires_at: datetime | None


class ChildRequestPage(BaseModel):
    items: list[ChildRequestDTO]
    next_cursor: str | None
    open_count: int


def _expire_open(db: Session) -> int:
    now = datetime.now(UTC)
    # Persist the state transition inside the current transaction before a
    # subsequent count/list. The session intentionally has autoflush disabled.
    return db.query(ChildRequest).filter(
        ChildRequest.status == "open",
        ChildRequest.expires_at.isnot(None),
        ChildRequest.expires_at <= now,
    ).update({ChildRequest.status: "expired"}, synchronize_session="fetch")


@router.post("", response_model=ChildRequestDTO, deprecated=True)
def create_child_request(
    req: ChildRequestCreate,
    request: Request,
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    raise HTTPException(410, "Exception requests are retired. GuardianNode now focuses on screenshot capture and AI review.")


@router.get("/mine", response_model=list[ChildRequestDTO])
def list_my_child_requests(
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    _expire_open(db)
    rows = (
        db.query(ChildRequest)
        .filter(ChildRequest.device_id == device.device_id)
        .order_by(ChildRequest.created_at.desc(), ChildRequest.request_id.desc())
        .limit(20)
        .all()
    )
    db.commit()
    return rows


@router.get("", response_model=ChildRequestPage)
def list_child_requests(
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_dep),
    _: User = Depends(parent_user),
):
    _expire_open(db)
    q = db.query(ChildRequest)
    if status:
        q = q.filter(ChildRequest.status == status)
    if cursor:
        anchor = db.get(ChildRequest, cursor)
        if anchor is None:
            raise HTTPException(400, "Invalid child-request cursor")
        q = q.filter(or_(
            ChildRequest.created_at < anchor.created_at,
            and_(
                ChildRequest.created_at == anchor.created_at,
                ChildRequest.request_id < anchor.request_id,
            ),
        ))
    rows = q.order_by(
        ChildRequest.created_at.desc(), ChildRequest.request_id.desc()
    ).limit(limit + 1).all()
    items = rows[:limit]
    next_cursor = items[-1].request_id if len(rows) > limit else None
    open_count = db.query(ChildRequest).filter(ChildRequest.status == "open").count()
    db.commit()
    return ChildRequestPage(
        items=[ChildRequestDTO.model_validate(item) for item in items],
        next_cursor=next_cursor,
        open_count=open_count,
    )


class ChildRequestReview(BaseModel):
    status: str = Field(pattern="^(approved|denied|dismissed)$")
    response_note: str | None = Field(default=None, max_length=4096)


@router.post("/{request_id}/review", response_model=ChildRequestDTO, deprecated=True)
def review_child_request(
    request_id: str,
    req: ChildRequestReview,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
):
    raise HTTPException(410, "Exception approvals are retired. Existing request history remains available for reference.")
