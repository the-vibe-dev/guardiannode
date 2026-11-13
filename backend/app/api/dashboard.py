"""Aggregated dashboard data for the overview page."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep, parent_user
from app.db.models import Alert, Device, Event, RiskResult, ScreenshotUploadReceipt, User
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


class CaptureDeviceStatus(BaseModel):
    device_id: str
    hostname: str
    connection_status: str
    latest_capture_at: datetime | None
    last_reviewed_at: datetime | None
    last_review_status: str
    classifier_status: str | None
    review_model: str | None
    pending_review_count: int
    reviewing_count: int
    waiting_upload_count: int | None
    queue_report_age_seconds: int | None


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
    devices: list[CaptureDeviceStatus] = Field(default_factory=list)
    review_failures_5m: int = 0


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
    _: User = Depends(parent_user),
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
    # A receipt or an image Event alone does not prove completed review. Join
    # the persisted RiskResult, then expose its degraded/rules-only state.
    last_reviewed_at = (
        db.query(func.max(RiskResult.created_at))
        .join(Event, RiskResult.event_id == Event.event_id)
        .filter(Event.source_type == "image", Event.deletion_state == "active")
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
    queues = {item["device_id"]: item for item in pipeline_metrics.agent_queues()}
    waiting_upload = sum(max(0, int(item.get("queued_frames", 0) or 0)) for item in queues.values())
    pending_by_device = screenshot_async.pending_counts_by_device()
    reviewing_by_device: dict[str, int] = {}
    for item in snapshot.get("in_flight", []):
        device_id = item.get("device_id")
        if isinstance(device_id, str):
            reviewing_by_device[device_id] = reviewing_by_device.get(device_id, 0) + 1
    device_statuses = []
    for device in db.query(Device).order_by(Device.created_at, Device.device_id).all():
        receipt = db.query(ScreenshotUploadReceipt).filter(
            ScreenshotUploadReceipt.device_id == device.device_id,
        ).order_by(ScreenshotUploadReceipt.created_at.desc(), ScreenshotUploadReceipt.id.desc()).first()
        latest = db.query(RiskResult, Event).join(
            Event, RiskResult.event_id == Event.event_id,
        ).filter(
            Event.device_id == device.device_id, Event.source_type == "image",
            Event.deletion_state == "active",
        ).order_by(RiskResult.created_at.desc(), RiskResult.risk_id.desc()).first()
        risk, event = latest if latest is not None else (None, None)
        if risk is None:
            review_status = "not_reviewed"
        elif risk.classifier_status == "no_text_to_review":
            review_status = "rules_only"
        elif risk.classifier_status != "ok":
            review_status = "degraded"
        elif (
            (event.event_metadata or {}).get("tier") == "rules_only" if event is not None else False
        ) or (risk.model or "").strip().lower().replace("-", "_") in {"rules", "rules_only", "local_rules"}:
            review_status = "rules_only"
        elif risk.model:
            review_status = "ai_reviewed"
        else:
            review_status = "degraded"
        report = queues.get(device.device_id)
        device_pending = pending_by_device.get(device.device_id, 0)
        device_statuses.append(CaptureDeviceStatus(
            device_id=device.device_id,
            hostname=device.hostname,
            connection_status=device.status,
            latest_capture_at=receipt.created_at if receipt else None,
            last_reviewed_at=risk.created_at if risk else None,
            last_review_status=review_status,
            classifier_status=risk.classifier_status if risk else None,
            review_model=risk.model if risk else None,
            pending_review_count=device_pending,
            reviewing_count=min(device_pending, reviewing_by_device.get(device.device_id, 0)),
            waiting_upload_count=max(0, int(report.get("queued_frames", 0) or 0)) if report else None,
            queue_report_age_seconds=int(report["age_seconds"]) if report and "age_seconds" in report else None,
        ))

    return CaptureStatus(
        latest_capture_at=latest_receipt.created_at if latest_receipt else None,
        latest_capture_device_id=latest_receipt.device_id if latest_receipt else None,
        latest_capture_hostname=latest_device.hostname if latest_device else None,
        pending_review_count=pending,
        reviewing_count=reviewing,
        waiting_upload_count=waiting_upload,
        estimated_wait_seconds=estimated_wait_seconds,
        last_reviewed_at=last_reviewed_at,
        devices=device_statuses,
        review_failures_5m=max(0, int(snapshot.get("failed_frames_in_window", 0) or 0)),
    )
