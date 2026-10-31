"""Append-only parental consent and monitoring gate."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import ConsentRecord, User

NOTICE_VERSION = "privacy-notice-2026-08-v1"


@dataclass(frozen=True)
class ProcessingPolicy:
    generation: str | None
    active: bool
    screenshots: bool
    apps_and_urls: bool
    retention: bool
    notifications: bool
    external_ai: bool


def effective_policy(session: Session) -> ProcessingPolicy:
    """Resolve the latest parent choices at a processing boundary.

    Capture needs durable retention because its upload/classification pipeline
    persists encrypted frames before analysis. Until an ephemeral pipeline is
    implemented, disabling retention also disables new capture.
    """
    if session.query(User).count() == 0:
        return ProcessingPolicy(None, True, True, True, True, True, False)
    row = latest(session)
    choices = row.choices or {} if row else {}
    active = bool(
        row and row.status == "granted" and row.notice_version == NOTICE_VERSION
        and choices.get("child_notice_acknowledged") is True
    )
    return ProcessingPolicy(
        row.consent_id if row else None,
        active,
        active and choices.get("screenshots") is True and choices.get("retention") is True,
        active and choices.get("apps_and_urls") is True and choices.get("retention") is True,
        active and choices.get("retention") is True,
        active and choices.get("notifications") is True,
        active and choices.get("external_ai") is True,
    )


def latest(session: Session) -> ConsentRecord | None:
    return session.query(ConsentRecord).order_by(ConsentRecord.created_at.desc()).first()


def monitoring_allowed(session: Session) -> bool:
    policy = effective_policy(session)
    return policy.active and (policy.screenshots or policy.apps_and_urls)
