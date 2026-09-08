"""Append-only parental consent and monitoring gate."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ConsentRecord, User

NOTICE_VERSION = "privacy-notice-2026-08-v1"


def latest(session: Session) -> ConsentRecord | None:
    return session.query(ConsentRecord).order_by(ConsentRecord.created_at.desc()).first()


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
