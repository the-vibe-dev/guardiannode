"""Cascade-safe deletion of events and their dependent records.

Events fan out into risk results, alerts, notification jobs, review feedback,
evidence rows, and encrypted files. SQLite enforces foreign keys, but these
relations do not have automatic cascades. Every delete path must use the same
dependency ordering and preserve failed file deletions for retry.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    Event,
    EvidenceBlob,
    GuardianReview,
    GuardianReviewFeedback,
    GuardianReviewPreview,
    NotificationJob,
    NotificationLog,
    RiskResult,
)
from app.services.evidence_paths import UnsafeEvidencePathError, resolve_stored_evidence_path

log = logging.getLogger(__name__)


def delete_blob(session: Session, blob: EvidenceBlob) -> bool:
    """Delete one blob only after its file is gone; retain failures for retry."""
    now = datetime.now(UTC)
    blob.deletion_state = "pending_delete"
    blob.delete_requested_at = blob.delete_requested_at or now
    blob.delete_attempts = int(blob.delete_attempts or 0) + 1
    try:
        # A prior unlink may have succeeded before a crash/DB rollback. The
        # absent owned file is already deleted; keep confinement/symlink checks
        # but let its database deletion and dependent cascade finish.
        resolve_stored_evidence_path(blob.encrypted_path, must_exist=False).unlink(missing_ok=True)
    except UnsafeEvidencePathError as e:
        blob.deletion_state = "delete_failed"
        blob.last_delete_error = str(e)[:2048]
        log.warning("refusing unsafe evidence deletion %s: %s", blob.encrypted_path, e)
        return False
    except Exception as e:
        blob.deletion_state = "delete_failed"
        blob.last_delete_error = str(e)[:2048]
        log.warning("could not unlink evidence file %s: %s", blob.encrypted_path, e)
        return False
    # A blob-only retention pass must also clear evidence pointers when an
    # earlier file deletion failed and is now being retried.
    session.query(Event).filter(Event.screenshot_blob_id == blob.blob_id).update(
        {Event.screenshot_blob_id: None}, synchronize_session="fetch"
    )
    session.query(Event).filter(Event.image_blob_id == blob.blob_id).update(
        {Event.image_blob_id: None}, synchronize_session="fetch"
    )
    session.delete(blob)
    return True


def delete_alerts(session: Session, alert_ids: Iterable[str]) -> dict[str, int]:
    """Remove alert-dependent private records before their foreign-key parents."""
    ids = list(dict.fromkeys(item for item in alert_ids if item))
    deleted = {"alerts": 0, "guardian_reviews": 0}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        review_ids = session.query(GuardianReview.review_id).filter(GuardianReview.alert_id.in_(chunk))
        session.query(GuardianReviewFeedback).filter(
            GuardianReviewFeedback.review_id.in_(review_ids)
        ).delete(synchronize_session=False)
        deleted["guardian_reviews"] += session.query(GuardianReview).filter(
            GuardianReview.alert_id.in_(chunk)
        ).delete(synchronize_session=False)
        session.query(GuardianReviewPreview).filter(
            GuardianReviewPreview.alert_id.in_(chunk)
        ).delete(synchronize_session=False)
        session.query(NotificationJob).filter(
            NotificationJob.alert_id.in_(chunk)
        ).delete(synchronize_session=False)
        session.query(NotificationLog).filter(
            NotificationLog.alert_id.in_(chunk)
        ).delete(synchronize_session=False)
        deleted["alerts"] += session.query(Alert).filter(
            Alert.alert_id.in_(chunk)
        ).delete(synchronize_session=False)
    return deleted


def delete_events(session: Session, event_ids: Iterable[str]) -> dict[str, int]:
    """Delete events plus their risk results, alerts, blob rows, and blob files.

    Returns counts per record type. Does not commit.
    """
    ids = [e for e in event_ids if e]
    deleted = {"events": 0, "risk_results": 0, "alerts": 0, "blobs": 0, "guardian_reviews": 0}
    if not ids:
        return deleted

    # Work in chunks: SQLite has a bound-parameter limit.
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]

        rows = session.query(Event).filter(Event.event_id.in_(chunk)).all()
        deletable_ids: list[str] = []
        for event in rows:
            blobs = session.query(EvidenceBlob).filter(EvidenceBlob.event_id == event.event_id).all()
            failed = False
            for blob in blobs:
                if delete_blob(session, blob):
                    deleted["blobs"] += 1
                else:
                    failed = True
            if not failed:
                deletable_ids.append(event.event_id)
            else:
                event.deletion_state = "pending_delete"
                event.deletion_requested_at = (
                    event.deletion_requested_at or datetime.now(UTC)
                )

        if not deletable_ids:
            continue
        risk_ids = [
            r[0] for r in session.query(RiskResult.risk_id)
            .filter(RiskResult.event_id.in_(deletable_ids)).all()
        ]
        if risk_ids:
            alert_ids = [
                row[0] for row in session.query(Alert.alert_id).filter(Alert.risk_id.in_(risk_ids)).all()
            ]
            for key, count in delete_alerts(session, alert_ids).items():
                deleted[key] += count
            deleted["risk_results"] += (
                session.query(RiskResult).filter(RiskResult.risk_id.in_(risk_ids)).delete(synchronize_session=False)
            )

        deleted["events"] += (
            session.query(Event).filter(Event.event_id.in_(deletable_ids)).delete(synchronize_session=False)
        )
    return deleted


def delete_orphaned_blob_files(session: Session) -> int:
    """Remove blob rows whose event no longer exists (defensive sweep)."""
    session.flush()  # make earlier pending deletes visible (autoflush may be off)
    n = 0
    orphans = (
        session.query(EvidenceBlob)
        .filter(~session.query(Event).filter(Event.event_id == EvidenceBlob.event_id).exists())
        .all()
    )
    for blob in orphans:
        if delete_blob(session, blob):
            n += 1
    return n


def retry_pending_deletions(session: Session, *, limit: int = 100) -> dict[str, int]:
    """Retry failed blob unlinks and finish their pending event cascades."""
    blobs = (
        session.query(EvidenceBlob)
        .filter(EvidenceBlob.deletion_state.in_(["pending_delete", "delete_failed"]))
        .order_by(EvidenceBlob.delete_requested_at.asc())
        .limit(limit)
        .all()
    )
    # Only an explicit full-event deletion may remove its context after a
    # retry. A screenshot-only expiry must keep the live event/risk/alert.
    event_ids = {
        row[0] for row in session.query(Event.event_id)
        .filter(Event.deletion_state == "pending_delete")
        .order_by(Event.deletion_requested_at.asc())
        .limit(limit).all()
    }
    removed = sum(1 for blob in blobs if delete_blob(session, blob))
    session.flush()
    finished = {"events": 0, "risk_results": 0, "alerts": 0, "blobs": removed, "guardian_reviews": 0}
    for event_id in event_ids:
        if session.query(EvidenceBlob).filter(EvidenceBlob.event_id == event_id).count() == 0:
            counts = delete_events(session, [event_id])
            for key, value in counts.items():
                finished[key] += value
    return finished
