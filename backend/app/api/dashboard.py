"""Aggregated dashboard data for the overview page."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep
from app.db.models import Alert, Device, User

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


def _count_since(db: Session, severity: str, since: datetime) -> int:
    return (
        db.query(func.count(Alert.alert_id))
        .filter(Alert.severity == severity, Alert.created_at >= since)
        .scalar()
        or 0
    )


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db_dep), _: User = Depends(current_user)):
    now = datetime.now(timezone.utc)
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
