"""Audit log helpers. Every sensitive action goes through here."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog

log = logging.getLogger("audit")


def log_action(
    session: Session,
    *,
    actor: str,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    source_ip: str | None = None,
) -> AuditLog:
    row = AuditLog(
        actor=actor,
        action=action,
        target=target,
        details=details or {},
        source_ip=source_ip,
    )
    session.add(row)
    session.flush()
    log.info("audit %s by %s on %s", action, actor, target or "-")
    return row
