"""Cascade-safe deletion of events and their dependent records.

Events fan out into RiskResults, Alerts, EvidenceBlob rows, and encrypted blob
files on disk. SQLite (as configured) does not enforce FK cascades, so every
delete path — retention cleanup and parent-initiated wipes — must go through
these helpers or it strands orphaned rows and undeletable evidence files.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    Event,
    EvidenceBlob,
    GuardianReview,
    GuardianReviewPreview,
    RiskResult,
)
from app.services.evidence_paths import UnsafeEvidencePathError, resolve_stored_evidence_path

log = logging.getLogger(__name__)


def delete_blob(session: Session, blob: EvidenceBlob) -> bool:
    """Delete one evidence blob row and its encrypted file. Returns True if the
    row was deleted (file-unlink failures are logged but don't strand the row)."""
    try:
        resolve_stored_evidence_path(blob.encrypted_path).unlink(missing_ok=True)
    except (FileNotFoundError, UnsafeEvidencePathError) as e:
        log.warning("skipping unsafe or missing evidence file %s: %s", blob.encrypted_path, e)
    except Exception as e:
        log.warning("could not unlink evidence file %s: %s", blob.encrypted_path, e)
    session.delete(blob)
    return True


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

        risk_ids = [
            r[0] for r in session.query(RiskResult.risk_id).filter(RiskResult.event_id.in_(chunk)).all()
        ]
        if risk_ids:
            alert_ids = [
                row[0] for row in session.query(Alert.alert_id).filter(Alert.risk_id.in_(risk_ids)).all()
            ]
            if alert_ids:
                preview_ids = [
                    row[0] for row in session.query(GuardianReviewPreview.preview_id)
                    .filter(GuardianReviewPreview.alert_id.in_(alert_ids)).all()
                ]
                deleted["guardian_reviews"] += session.query(GuardianReview).filter(
                    GuardianReview.alert_id.in_(alert_ids)
                ).delete(synchronize_session=False)
                if preview_ids:
                    session.query(GuardianReviewPreview).filter(
                        GuardianReviewPreview.preview_id.in_(preview_ids)
                    ).delete(synchronize_session=False)
            deleted["alerts"] += (
                session.query(Alert).filter(Alert.risk_id.in_(risk_ids)).delete(synchronize_session=False)
            )
            deleted["risk_results"] += (
                session.query(RiskResult).filter(RiskResult.risk_id.in_(risk_ids)).delete(synchronize_session=False)
            )

        for blob in session.query(EvidenceBlob).filter(EvidenceBlob.event_id.in_(chunk)).all():
            delete_blob(session, blob)
            deleted["blobs"] += 1

        deleted["events"] += (
            session.query(Event).filter(Event.event_id.in_(chunk)).delete(synchronize_session=False)
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
        delete_blob(session, blob)
        n += 1
    return n
