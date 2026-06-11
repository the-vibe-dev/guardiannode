"""Retention cleanup: drop expired events, alerts, evidence per policy."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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
    """Run a single cleanup pass. Returns counts of deleted rows by category.

    Deletion always removes the whole record chain (event → risk result →
    alert → evidence blob row + file) via :mod:`app.services.purge` so cleanup
    never strands orphans.
    """
    from app.services import purge

    r = {**DEFAULT_RETENTION_DAYS, **(retention or {})}
    deleted = {"alerts": 0, "risk_results": 0, "events": 0, "blobs": 0, "audit": 0}

    # 1) Per severity tier: expire the full event chain past its window.
    #    ("none"-level results share the "low" tier — they're the bulk noise.)
    for sev_group, days in (("low", r["low"]), ("medium", r["medium"]),
                            ("high", r["high"]), ("critical", r["critical"])):
        if days <= 0:
            continue
        cutoff = _cutoff(days)
        levels = ["none", "low"] if sev_group == "low" else [sev_group]
        event_ids = [
            row[0]
            for row in session.query(RiskResult.event_id)
            .filter(RiskResult.risk_level.in_(levels), RiskResult.created_at < cutoff)
            .all()
        ]
        counts = purge.delete_events(session, event_ids)
        for key in ("alerts", "risk_results", "events", "blobs"):
            deleted[key] += counts[key]

        # Defensive: also expire alert rows of this severity whose chain is
        # already gone (e.g. rows from before cascade deletion existed).
        sev_levels = ["low"] if sev_group == "low" else [sev_group]
        deleted["alerts"] += (
            session.query(Alert)
            .filter(Alert.severity.in_(sev_levels), Alert.created_at < cutoff)
            .delete(synchronize_session=False)
        )

    # 2) Events that never got a risk result (ingest interrupted mid-pipeline).
    cutoff = _cutoff(max(r["low"], 1))
    orphan_event_ids = [
        row[0]
        for row in session.query(Event.event_id)
        .filter(
            Event.timestamp < cutoff,
            ~session.query(RiskResult).filter(RiskResult.event_id == Event.event_id).exists(),
        )
        .all()
    ]
    counts = purge.delete_events(session, orphan_event_ids)
    for key in ("alerts", "risk_results", "events", "blobs"):
        deleted[key] += counts[key]

    # 3) Flagged screenshots age out earlier than their alert metadata: drop the
    #    blob (row + encrypted file) but keep event/risk/alert for context.
    blob_cutoff = _cutoff(r["screenshots_flagged"])
    if r["screenshots_flagged"] > 0:
        for blob in (
            session.query(EvidenceBlob).filter(EvidenceBlob.created_at < blob_cutoff).all()
        ):
            for ev in session.query(Event).filter(Event.screenshot_blob_id == blob.blob_id).all():
                ev.screenshot_blob_id = None
            for ev in session.query(Event).filter(Event.image_blob_id == blob.blob_id).all():
                ev.image_blob_id = None
            purge.delete_blob(session, blob)
            deleted["blobs"] += 1

    # 4) Defensive sweep: blob rows whose event vanished some other way.
    deleted["blobs"] += purge.delete_orphaned_blob_files(session)

    # 5) Audit logs
    audit_cutoff = _cutoff(r["audit_logs"])
    audit_q = session.query(AuditLog).filter(AuditLog.created_at < audit_cutoff)
    deleted["audit"] += audit_q.delete(synchronize_session=False)

    session.commit()
    return deleted
