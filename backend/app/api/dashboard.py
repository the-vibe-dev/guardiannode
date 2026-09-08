"""Aggregated dashboard data for the overview page."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep
from app.db.models import Alert, Device, Event, ScreenshotUploadReceipt, User
from app.services import pipeline_metrics, screenshot_async

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class Counts(BaseModel):
    critical: int
    high: int
    medium: int
    low: int


class Overview(BaseModel):
    counts_24h: Counts
    counts_7d: Counts
    open_alert_count: int
    devices_total: int
    devices_online: int
    devices_paused: int
    recent_severity_counts: dict[str, int]  # by day (last 14 days)


class CaptureStatus(BaseModel):
    """Metadata-only receipt and review progress for screen captures."""

    latest_capture_at: datetime | None
    latest_capture_device_id: str | None
    latest_capture_hostname: str | None
    pending_review_count: int
    reviewing_count: int
    waiting_upload_count: int
    estimated_wait_seconds: int | None
    last_reviewed_at: datetime | None


def _count_since(db: Session, severity: str, since: datetime) -> int:
    return (
        db.query(func.count(Alert.alert_id))
        .filter(Alert.severity == severity, Alert.created_at >= since)
        .scalar()
        or 0
    )


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db_dep), _: User = Depends(current_user)):
    now = datetime.now(UTC)
    h24 = now - timedelta(hours=24)
    d7 = now - timedelta(days=7)

    counts_24h = Counts(
        critical=_count_since(db, "critical", h24),
        high=_count_since(db, "high", h24),
        medium=_count_since(db, "medium", h24),
        low=_count_since(db, "low", h24),
    )
    counts_7d = Counts(
        critical=_count_since(db, "critical", d7),
        high=_count_since(db, "high", d7),
        medium=_count_since(db, "medium", d7),
        low=_count_since(db, "low", d7),
    )
    open_alerts = db.query(func.count(Alert.alert_id)).filter(Alert.status == "open").scalar() or 0
    devices_total = db.query(func.count(Device.device_id)).scalar() or 0
    devices_online = (
        db.query(func.count(Device.device_id)).filter(Device.status == "online").scalar() or 0
    )
    devices_paused = (
        db.query(func.count(Device.device_id)).filter(Device.status == "paused").scalar() or 0
    )

    by_day: dict[str, int] = {}
    for i in range(14):
        day = (now - timedelta(days=i)).date().isoformat()
        n = (
            db.query(func.count(Alert.alert_id))
            .filter(Alert.created_at >= now - timedelta(days=i + 1))
            .filter(Alert.created_at < now - timedelta(days=i))
            .scalar()
            or 0
        )
        by_day[day] = n

    return Overview(
        counts_24h=counts_24h,
        counts_7d=counts_7d,
        open_alert_count=open_alerts,
        devices_total=devices_total,
        devices_online=devices_online,
        devices_paused=devices_paused,
        recent_severity_counts=by_day,
    )


@router.get("/capture-status", response_model=CaptureStatus)
def capture_status(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
) -> CaptureStatus:
    """Show acceptance separately from classification and alert creation.

    This intentionally returns receipt/progress metadata only. It never returns
    screenshot bytes, OCR text, window titles, URLs, or classification content.
    """
    latest_receipt = (
        db.query(ScreenshotUploadReceipt)
        .order_by(
            ScreenshotUploadReceipt.created_at.desc(),
            ScreenshotUploadReceipt.id.desc(),
        )
        .first()
    )
    latest_device = (
        db.get(Device, latest_receipt.device_id) if latest_receipt is not None else None
    )
    last_reviewed_at = (
        db.query(func.max(Event.received_at))
        .filter(Event.source_type == "image")
        .scalar()
    )

    pending = screenshot_async.pending_count()
    snapshot = pipeline_metrics.snapshot(window_seconds=300)
    reviewing = min(pending, int(snapshot.get("in_flight_count", 0) or 0))
    throughput = snapshot.get("throughput", {})
    latency_ms = int(
        throughput.get("p50_latency_ms")
        or throughput.get("avg_latency_ms")
        or 0
    )
    estimated_wait_seconds = (
        max(1, round(pending * latency_ms / 1000))
        if pending > 0 and latency_ms > 0
        else None
    )
    waiting_upload = sum(
        max(0, int(item.get("queued_frames", 0) or 0))
        for item in pipeline_metrics.agent_queues()
    )

    return CaptureStatus(
        latest_capture_at=latest_receipt.created_at if latest_receipt else None,
        latest_capture_device_id=latest_receipt.device_id if latest_receipt else None,
        latest_capture_hostname=latest_device.hostname if latest_device else None,
        pending_review_count=pending,
        reviewing_count=reviewing,
        waiting_upload_count=waiting_upload,
        estimated_wait_seconds=estimated_wait_seconds,
        last_reviewed_at=last_reviewed_at,
    )
