"""Append-only parental consent and monitoring gate."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ConsentRecord, User

NOTICE_VERSION = "privacy-notice-2026-08-v1"


def latest(session: Session) -> ConsentRecord | None:
    return session.query(ConsentRecord).order_by(
        ConsentRecord.created_at.desc(), ConsentRecord.consent_id.desc()
    ).first()


def monitoring_allowed(session: Session) -> bool:
    # Setup/bootstrap may run before the first administrator exists. Once the
    # family account exists, explicit current-version consent is mandatory.
    if session.query(User).count() == 0:
        return True
    row = latest(session)
    return bool(
        row
        and row.status == "granted"
        and row.notice_version == NOTICE_VERSION
        and row.choices.get("child_notice_acknowledged") is True
    )


def choice_allowed(session: Session, choice: str) -> bool:
    """Apply current choices at use time, including jobs queued before a change.

    The no-account path remains available to local bootstrap/synthetic harnesses;
    a configured family must have an active, current, explicitly selected choice.
    """
    if session.query(User).count() == 0:
        return True
    row = latest(session)
    return bool(
        row and row.status == "granted"
        and row.notice_version == NOTICE_VERSION
        and row.choices.get("child_notice_acknowledged") is True
        and row.choices.get(choice) is True
    )


def processing_allowed(session: Session, *, screenshots: bool = False) -> bool:
    # This version's monitoring pipeline necessarily stores alert/event history.
    # Until an ephemeral pipeline exists, declining retention pauses collection.
    return choice_allowed(session, "retention") and (
        not screenshots or choice_allowed(session, "screenshots")
    )


def collection_allowed(session: Session, *, screenshots: bool = False) -> bool:
    """Public device collection waits for completed family setup and consent."""
    return session.query(User).count() > 0 and processing_allowed(session, screenshots=screenshots)
