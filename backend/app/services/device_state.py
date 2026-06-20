"""Shared device pause-state logic.

A device is paused only while ``paused_until`` is in the future. Anything that
honors pause state MUST go through :func:`is_device_paused` — comparing
``paused_until is not None`` is wrong because an expired pause would silently
keep protection off forever.

The helper also self-heals: when it sees an expired pause it clears the column
and flips the status back to ``online``, so the dashboard never shows a stale
"paused" badge. Callers are responsible for committing the session.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Device


def _as_utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; all GuardianNode timestamps are UTC.
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_device_paused(device: Device | None, *, now: datetime | None = None) -> bool:
    """Return True only while the device's pause window is currently active.

    Clears expired pauses in place (caller commits): ``paused_until`` is set
    back to None and a "paused" status returns to "online" so a lapsed pause
    can never keep monitoring disabled.
    """
    if device is None or device.paused_until is None:
        return False
    now = now or datetime.now(timezone.utc)
    if _as_utc(device.paused_until) > now:
        return True
    # Pause has lapsed — clear it server-side.
    device.paused_until = None
    if device.status == "paused":
        device.status = "online"
    return False


def effective_paused_until(device: Device | None, *, now: datetime | None = None) -> datetime | None:
    """The pause expiry if (and only if) the pause is still active."""
    if device is None:
        return None
    return device.paused_until if is_device_paused(device, now=now) else None
