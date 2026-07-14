"""Shared FastAPI dependencies (auth + db)."""
from __future__ import annotations

import logging
import time
from collections.abc import Generator
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.db.models import Device, User
from app.db.session import get_db
from app.services import device_tokens, rate_limit
from app.services.audit import log_action

log = logging.getLogger(__name__)


def get_db_dep() -> Generator[Session, None, None]:  # pragma: no cover - thin wrapper
    yield from get_db()


def _clear_expired_session(request: Request) -> None:
    csrf_token = request.session.get("csrf_token")
    request.session.clear()
    if csrf_token:
        request.session["csrf_token"] = csrf_token


def _session_float(request: Request, key: str) -> float | None:
    value = request.session.get(key)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def current_user(request: Request, db: Session = Depends(get_db_dep)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    now = time.time()
    login_at = _session_float(request, "login_at")
    if login_at is None:
        _clear_expired_session(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if settings_mod.settings.session_absolute_timeout_seconds > 0:
        if now - login_at > settings_mod.settings.session_absolute_timeout_seconds:
            _clear_expired_session(request)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    last_activity_at = _session_float(request, "last_activity_at") or login_at
    if settings_mod.settings.session_idle_timeout_seconds > 0:
        if now - last_activity_at > settings_mod.settings.session_idle_timeout_seconds:
            _clear_expired_session(request)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.get(User, user_id)
    if user is None:
        _clear_expired_session(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.session_revoked_at is not None and login_at <= _timestamp(user.session_revoked_at):
        _clear_expired_session(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
    request.session["last_activity_at"] = now
    return user


def _require_step_up(
    request: Request,
    db: Session,
    user: User,
    *,
    level: str,
    timeout_seconds: int,
) -> None:
    ts = request.session.get("reauth_at") or request.session.get("login_at")
    try:
        authenticated_at = float(str(ts))
    except (TypeError, ValueError):
        authenticated_at = 0
    if timeout_seconds > 0 and time.time() - authenticated_at <= timeout_seconds:
        return
    log_action(
        db,
        actor=str(user.id),
        action="auth.step_up.denied",
        details={"level": level, "path": request.url.path, "method": request.method},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    raise HTTPException(
        status_code=403,
        detail={
            "code": "step_up_required",
            "level": level,
            "method": "password",
            "action": f"{request.method} {request.url.path}",
        },
    )


def require_recent_auth(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
) -> None:
    """Require standard recent parent authentication for a sensitive action."""
    _require_step_up(
        request, db, user, level="standard",
        timeout_seconds=settings_mod.settings.recent_auth_timeout_seconds,
    )


def require_critical_auth(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
) -> None:
    """Require the shorter key/transport/update authentication window."""
    _require_step_up(
        request, db, user, level="critical",
        timeout_seconds=settings_mod.settings.critical_auth_timeout_seconds,
    )


def parent_user(user: User = Depends(current_user)) -> User:
    """Allow safety-review access only to decision-making parent roles."""
    if user.role not in {"admin", "parent"}:
        raise HTTPException(status_code=403, detail="Parent role required")
    return user


def current_device(request: Request, db: Session = Depends(get_db_dep)) -> Device:
    """Authenticate a device via Authorization: Bearer <token>.

    Invalid attempts are rate-limited per client IP: Argon2 verification is
    expensive by design, so unauthenticated callers must not get to trigger it
    repeatedly for free.
    """
    client_ip = request.client.host if request.client else "unknown"
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    blocked, retry_after = rate_limit.is_blocked("device_auth", client_ip)
    if blocked:
        # A child can legitimately recover from stale bad credentials by
        # re-pairing. Let a valid structured token clear its own IP's failure
        # window; keep blocked legacy/garbage tokens cheap.
        if device_tokens.parse_token(token) is not None:
            device = device_tokens.authenticate(db, token)
            if device is not None:
                rate_limit.reset("device_auth", client_ip)
                return device
        raise HTTPException(
            status_code=429,
            detail="Too many failed device authentication attempts.",
            headers={"Retry-After": str(retry_after)},
        )

    device = device_tokens.authenticate(db, token)
    if device is not None:
        rate_limit.reset("device_auth", client_ip)
        return device

    rate_limit.record_failure("device_auth", client_ip)
    log.warning("invalid device token from %s", client_ip)
    raise HTTPException(status_code=401, detail="Invalid device token")
