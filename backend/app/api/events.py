"""Event ingestion + listing."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_device, current_user, get_db_dep
from app.db.models import Device, Event, User
from app.services import event_ingest, encryption, screenshot_async, screenshot_ingest
from app.services.device_state import is_device_paused

router = APIRouter(prefix="/events", tags=["events"])


class IngestRequest(BaseModel):
    event_id: str | None = None
    profile_id: str | None = None
    source_type: str
    app_name: str | None = None
    window_title: str | None = None
    url: str | None = None
    timestamp: str | None = None
    redacted_text: str | None = None
    evidence_type: str = "visible_text"
    age_group: str | None = None
    capture_scope: str = "browser_dom"
    policy_id: str | None = None
    policy_version: str | None = None
    collector_version: str | None = None
    screenshot_blob_id: str | None = None
    image_blob_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    event_id: str
    risk_id: str | None
    alert_id: str | None
    risk_level: str
    score: int
    categories: list[str]


@router.post("", response_model=IngestResponse)
async def ingest(
    req: IngestRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    if is_device_paused(device):
        # Quietly accept but don't store — pause behavior is honored server-side too
        return IngestResponse(
            event_id=req.event_id or "",
            risk_id=None,
            alert_id=None,
            risk_level="none",
            score=0,
            categories=[],
        )
    result = await event_ingest.ingest_event(
        db,
        payload=req.model_dump(),
        device_id=device.device_id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return IngestResponse(**result)


class EventDTO(BaseModel):
    event_id: str
    device_id: str
    profile_id: str | None
    source_type: str
    app_name: str | None
    window_title: str | None
    url: str | None
    timestamp: datetime
    received_at: datetime
    evidence_type: str
    has_text: bool
    has_screenshot: bool


def _to_dto(e: Event) -> EventDTO:
    return EventDTO(
        event_id=e.event_id,
        device_id=e.device_id,
        profile_id=e.profile_id,
        source_type=e.source_type,
        app_name=e.app_name,
        window_title=e.window_title,
        url=e.url,
        timestamp=e.timestamp,
        received_at=e.received_at,
        evidence_type=e.evidence_type,
        has_text=e.redacted_text_enc is not None,
        has_screenshot=e.screenshot_blob_id is not None,
    )


@router.get("", response_model=list[EventDTO])
def list_events(
    device_id: str | None = None,
    profile_id: str | None = None,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    q = db.query(Event).order_by(Event.timestamp.desc())
    if device_id:
        q = q.filter(Event.device_id == device_id)
    if profile_id:
        q = q.filter(Event.profile_id == profile_id)
    rows = q.limit(limit).all()
    return [_to_dto(e) for e in rows]


@router.get("/{event_id}/text")
def get_event_text(
    event_id: str,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    e = db.get(Event, event_id)
    if e is None:
        raise HTTPException(404, "Not found")
    if not e.redacted_text_enc:
        return {"text": ""}
    try:
        plain = encryption.decrypt_text(e.redacted_text_enc)
    except Exception:
        raise HTTPException(500, "Decryption failed")
    from app.services.audit import log_action
    log_action(db, actor=str(user.id), action="evidence.view_text", target=event_id)
    db.commit()
    return {"text": plain}


class ScreenshotIngestResponse(BaseModel):
    # The frame is stored the instant it arrives and classified by a background
    # worker, so the agent gets a fast ack and frames survive a child power-off.
    event_id: str
    status: str  # "queued" | "paused"
    queued: bool


@router.post("/screenshot", response_model=ScreenshotIngestResponse)
async def ingest_screenshot(
    request: Request,
    image: UploadFile = File(...),
    app_name: str | None = Form(default=None),
    window_title: str | None = Form(default=None),
    url: str | None = Form(default=None),
    profile_id: str | None = Form(default=None),
    age_group: str = Form(default="10_13"),
    capture_scope: str = Form(default="monitored_app"),
    policy_id: str | None = Form(default=None),
    policy_version: str | None = Form(default=None),
    collector_version: str | None = Form(default=None),
    timestamp: str | None = Form(default=None),
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    """Receive a raw screenshot, persist it immediately, and queue it for
    background classification (vision LLM → rules → alert). Returns fast so the
    agent's local queue never backs up and frames aren't lost on power-off."""
    if is_device_paused(device):
        # Honor pause server-side: drop quietly, don't store.
        return ScreenshotIngestResponse(event_id="", status="paused", queued=False)

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Empty image")
    if len(image_bytes) > 8 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 8 MB)")

    # Update device liveness now (don't wait for classification).
    device.last_seen = datetime.now(timezone.utc)
    if device.status not in ("paused", "disabled"):
        device.status = "online"
    db.commit()

    token = screenshot_async.store_pending(
        image_bytes,
        {
            "device_id": device.device_id,
            "app_name": app_name,
            "window_title": window_title,
            "url": url,
            "profile_id": profile_id,
            "age_group": age_group,
            "capture_scope": capture_scope,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "collector_version": collector_version,
            "timestamp": timestamp,
            "source_ip": request.client.host if request.client else None,
        },
    )
    await screenshot_async.enqueue(token)
    return ScreenshotIngestResponse(event_id=token, status="queued", queued=True)


@router.get("/{event_id}/screenshot")
def get_event_screenshot(
    event_id: str,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    """Return the decrypted screenshot bytes for a flagged event (parent dashboard only)."""
    from fastapi.responses import Response
    from app.db.models import EvidenceBlob
    e = db.get(Event, event_id)
    if e is None or not e.screenshot_blob_id:
        raise HTTPException(404, "No screenshot")
    blob = db.get(EvidenceBlob, e.screenshot_blob_id)
    if blob is None:
        raise HTTPException(404, "Blob missing")
    from pathlib import Path
    try:
        pt = encryption.decrypt_blob_from_disk(Path(blob.encrypted_path), aad=blob.blob_id.encode("ascii"))
    except Exception:
        raise HTTPException(500, "Decryption failed")
    from app.services.audit import log_action
    log_action(db, actor=str(user.id), action="evidence.view", target=event_id)
    db.commit()
    return Response(content=pt, media_type=blob.mime_type or "image/jpeg")
