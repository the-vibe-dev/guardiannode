"""Event ingestion + listing."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_device, current_user, get_db_dep
from app.db.models import Device, Event, User
from app.services import event_ingest, encryption, screenshot_async, screenshot_ingest
from app.services.device_state import is_device_paused

router = APIRouter(prefix="/events", tags=["events"])
_MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
_MAX_SCREENSHOT_PIXELS = 16_000_000
_MAX_SCREENSHOT_EDGE = 7680
Image.MAX_IMAGE_PIXELS = _MAX_SCREENSHOT_PIXELS


async def _read_upload_with_cap(image: UploadFile, limit: int = _MAX_SCREENSHOT_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await image.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, "Image too large (max 8 MB)")
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_image_bytes(image_bytes: bytes) -> str:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            image_format = img.format
            if image_format not in {"JPEG", "PNG"}:
                raise HTTPException(400, "Screenshot must be JPEG or PNG")
            width, height = img.size
            if width <= 0 or height <= 0:
                raise HTTPException(400, "Invalid screenshot dimensions")
            if width > _MAX_SCREENSHOT_EDGE or height > _MAX_SCREENSHOT_EDGE:
                raise HTTPException(400, "Screenshot dimensions are too large")
            if width * height > _MAX_SCREENSHOT_PIXELS:
                raise HTTPException(400, "Screenshot pixel count is too large")
            img.verify()
            return "image/jpeg" if image_format == "JPEG" else "image/png"
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "Invalid screenshot image")


class IngestRequest(BaseModel):
    event_id: str | None = Field(default=None, max_length=64)
    profile_id: str | None = Field(default=None, max_length=64)
    source_type: str = Field(max_length=32)
    app_name: str | None = Field(default=None, max_length=256)
    window_title: str | None = Field(default=None, max_length=1024)
    url: str | None = Field(default=None, max_length=4096)
    timestamp: str | None = Field(default=None, max_length=64)
    redacted_text: str | None = Field(default=None, max_length=200_000)
    evidence_type: str = Field(default="visible_text", max_length=32)
    age_group: str | None = Field(default=None, max_length=16)
    capture_scope: str = Field(default="browser_dom", max_length=64)
    policy_id: str | None = Field(default=None, max_length=64)
    policy_version: str | None = Field(default=None, max_length=64)
    collector_version: str | None = Field(default=None, max_length=64)
    screenshot_blob_id: str | None = Field(default=None, max_length=64)
    image_blob_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=100)


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
    app_name: str | None = Form(default=None, max_length=256),
    window_title: str | None = Form(default=None, max_length=1024),
    url: str | None = Form(default=None, max_length=4096),
    profile_id: str | None = Form(default=None, max_length=64),
    age_group: str = Form(default="10_13", max_length=16),
    capture_scope: str = Form(default="monitored_app", max_length=64),
    policy_id: str | None = Form(default=None, max_length=64),
    policy_version: str | None = Form(default=None, max_length=64),
    collector_version: str | None = Form(default=None, max_length=64),
    timestamp: str | None = Form(default=None, max_length=64),
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    """Receive a raw screenshot, persist it immediately, and queue it for
    background classification (vision LLM → rules → alert). Returns fast so the
    agent's local queue never backs up and frames aren't lost on power-off."""
    if is_device_paused(device):
        # Honor pause server-side: drop quietly, don't store.
        return ScreenshotIngestResponse(event_id="", status="paused", queued=False)

    if screenshot_async.pending_count() >= screenshot_async.max_pending():
        raise HTTPException(
            503,
            "Screenshot classifier backlog is full",
            headers={"Retry-After": "30"},
        )

    image_bytes = await _read_upload_with_cap(image)
    if not image_bytes:
        raise HTTPException(400, "Empty image")
    if age_group not in {"under_10", "10_13", "14_17"}:
        raise HTTPException(400, "Invalid age group")
    if capture_scope not in {"monitored_app", "visible_desktop", "browser_dom"}:
        raise HTTPException(400, "Invalid capture scope")
    mime_type = _validate_image_bytes(image_bytes)

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
            "mime_type": mime_type,
            "source_ip": request.client.host if request.client else None,
        },
    )
    if not screenshot_async.enqueue_nowait(token):
        screenshot_async.discard(token)
        raise HTTPException(
            503,
            "Screenshot classifier backlog is full",
            headers={"Retry-After": "30"},
        )
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
