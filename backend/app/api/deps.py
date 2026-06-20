"""Shared FastAPI dependencies (auth + db)."""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import Device, User
from app.db.session import get_db
from app.services import device_tokens, rate_limit

log = logging.getLogger(__name__)


def get_db_dep() -> Session:  # pragma: no cover - thin wrapper
    yield from get_db()


def current_user(request: Request, db: Session = Depends(get_db_dep)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def current_device(request: Request, db: Session = Depends(get_db_dep)) -> Device:
    """Authenticate a device via Authorization: Bearer <token>.

    Invalid attempts are rate-limited per client IP: Argon2 verification is
    expensive by design, so unauthenticated callers must not get to trigger it
    repeatedly for free.
    """
    client_ip = request.client.host if request.client else "unknown"
    blocked, retry_after = rate_limit.is_blocked("device_auth", client_ip)
    if blocked:
        raise HTTPException(
            status_code=429,
            detail="Too many failed device authentication attempts.",
            headers={"Retry-After": str(retry_after)},
        )

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    device = device_tokens.authenticate(db, token)
    if device is not None:
        rate_limit.reset("device_auth", client_ip)
        return device

    rate_limit.record_failure("device_auth", client_ip)
    log.warning("invalid device token from %s", client_ip)
    raise HTTPException(status_code=401, detail="Invalid device token")
