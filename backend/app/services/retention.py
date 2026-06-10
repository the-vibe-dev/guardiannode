"""Retention cleanup: drop expired events, alerts, evidence per policy."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert, AuditLog, EvidenceBlob, Event, RiskResult

log = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = {
    "critical": 90,
    "high": 90,
    "medium": 30,
    "low": 1,
    "none": 0,  # not stored long-term unless flagged
    "screenshots_flagged": 30,
    "audit_logs": 180,
}


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def run_cleanup(session: Session, retention: dict[str, int] | None = None) -> dict[str, int]:
    """Run a single cleanup pass. Returns counts of deleted rows by category."""
    r = {**DEFAULT_RETENTION_DAYS, **(retention or {})}
    deleted = {"alerts": 0, "risk_results": 0, "events": 0, "blobs": 0, "audit": 0}

    # 1) Alerts: per severity
    for sev, days in (("low", r["low"]), ("medium", r["medium"]),
                      ("high", r["high"]), ("critical", r["critical"])):
        if days <= 0:
            continue
        cutoff = _cutoff(days)
        q = session.query(Alert).filter(Alert.severity == sev, Alert.created_at < cutoff)
        n = q.delete(synchronize_session=False)
        deleted["alerts"] += n

    # 2) Orphan risk_results (no alert anymore and older than the lowest tier)
    cutoff = _cutoff(r["medium"])
    orphan_rr = (
        session.query(RiskResult)
        .filter(
            RiskResult.created_at < cutoff,
            ~session.query(Alert).filter(Alert.risk_id == RiskResult.risk_id).exists(),
        )
    )
    deleted["risk_results"] += orphan_rr.delete(synchronize_session=False)

    # 3) Orphan events (no RiskResult and no flagged blob)
    cutoff = _cutoff(r["low"])
    orphan_events = (
        session.query(Event)
        .filter(
            Event.timestamp < cutoff,
            ~session.query(RiskResult).filter(RiskResult.event_id == Event.event_id).exists(),
        )
    )
    deleted["events"] += orphan_events.delete(synchronize_session=False)

    # 4) Evidence blobs: keep alongside non-deleted referencing events
    blob_cutoff = _cutoff(r["screenshots_flagged"])
    # NULL blob ids must be excluded: SQL `NOT IN (… NULL …)` evaluates to NULL for
    # every row, so leaving the NULLs in would silently prevent all blob cleanup.
    referenced = (
        select(Event.screenshot_blob_id).where(Event.screenshot_blob_id.isnot(None))
        .union(select(Event.image_blob_id).where(Event.image_blob_id.isnot(None)))
    )
    stale_blobs = (
        session.query(EvidenceBlob)
        .filter(
            EvidenceBlob.created_at < blob_cutoff,
            ~EvidenceBlob.blob_id.in_(referenced),
        )
        .all()
    )
    for blob in stale_blobs:
        try:
            Path(blob.encrypted_path).unlink(missing_ok=True)
        except Exception as e:
            log.warning("blob unlink failed: %s", e)
        session.delete(blob)
        deleted["blobs"] += 1

    # 5) Audit logs
    audit_cutoff = _cutoff(r["audit_logs"])
    audit_q = session.query(AuditLog).filter(AuditLog.created_at < audit_cutoff)
    deleted["audit"] += audit_q.delete(synchronize_session=False)

    session.commit()
    return deleted
