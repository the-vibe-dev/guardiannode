"""Child-originated requests for time/site/app exceptions."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ulid import ULID

from app.api.deps import current_device, current_user, get_db_dep
from app.db.models import ChildRequest, Device, User
from app.services.audit import log_action

router = APIRouter(prefix="/child-requests", tags=["child-requests"])


class ChildRequestCreate(BaseModel):
    request_type: str = Field(pattern="^(more_time|site_exception|app_exception|other)$")
    target: str | None = Field(default=None, max_length=1024)
    reason: str | None = Field(default=None, max_length=4096)
    profile_id: str | None = None


class ChildRequestDTO(BaseModel):
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


@router.post("", response_model=ChildRequestDTO)
def create_child_request(
    req: ChildRequestCreate,
    request: Request,
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    row = ChildRequest(
        request_id=str(ULID()),
        device_id=device.device_id,
        profile_id=req.profile_id,
        request_type=req.request_type,
        target=req.target,
        reason=req.reason,
        status="open",
    )
    db.add(row)
    log_action(
        db,
        actor=device.device_id,
        action="child_request.create",
        target=row.request_id,
        details={"request_type": row.request_type, "target": row.target},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return row


@router.get("", response_model=list[ChildRequestDTO])
def list_child_requests(
    status: str | None = None,
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    q = db.query(ChildRequest).order_by(ChildRequest.created_at.desc())
    if status:
        q = q.filter(ChildRequest.status == status)
    return q.limit(200).all()


class ChildRequestReview(BaseModel):
    status: str = Field(pattern="^(approved|denied|dismissed)$")
    response_note: str | None = Field(default=None, max_length=4096)


@router.post("/{request_id}/review", response_model=ChildRequestDTO)
def review_child_request(
    request_id: str,
    req: ChildRequestReview,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    row = db.get(ChildRequest, request_id)
    if row is None:
        raise HTTPException(404, "Request not found")
    row.status = req.status
    row.response_note = req.response_note
    row.reviewed_by = str(user.id)
    row.reviewed_at = datetime.now(timezone.utc)
    log_action(
        db,
        actor=str(user.id),
        action="child_request.review",
        target=request_id,
        details={"status": req.status},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return row
