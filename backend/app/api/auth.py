"""Authentication: login, logout, current user, password reset via recovery code."""
from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.api.deps import current_user, get_db_dep, require_recent_auth
from app.db.models import User
from app.db.session import begin_immediate_if_sqlite
from app.services import rate_limit
from app.services.audit import log_action
from app.services.parent_auth import (
    hash_password,
    hash_recovery_code,
    verify_password,
    verify_recovery_code,
)
from app.services.setup_token import consume_setup_token, verify_setup_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    display_name: str
    role: str


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(scope: str, request: Request) -> None:
    blocked, retry_after = rate_limit.is_blocked(scope, _client_ip(request))
    if blocked:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _mark_session_authenticated(request: Request, user: User) -> None:
    now = time.time()
    request.session["user_id"] = user.id
    request.session["login_at"] = now
    request.session["reauth_at"] = now
    request.session["reauth_method"] = "password"
    request.session["last_activity_at"] = now
    user.last_login = datetime.fromtimestamp(now, UTC)


@router.get("/csrf")
def csrf_token(request: Request):
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return {"csrf_token": token}


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db_dep)):
    _enforce_rate_limit("login", request)
    user = db.query(User).filter(User.role == "admin").first()
    if user is None:
        raise HTTPException(status_code=400, detail="Setup not complete")
    if not verify_password(req.password, user.password_hash):
        rate_limit.record_failure("login", _client_ip(request))
        log_action(
            db, actor="anonymous", action="auth.login.fail",
            target=str(user.id),
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    rate_limit.reset("login", _client_ip(request))
    _mark_session_authenticated(request, user)
    log_action(
        db, actor=str(user.id), action="auth.login.success",
        target=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return LoginResponse(display_name=user.display_name, role=user.role)


@router.post("/reauth")
def reauth(req: LoginRequest, request: Request, db: Session = Depends(get_db_dep), user: User = Depends(current_user)):
    _enforce_rate_limit("reauth", request)
    if not verify_password(req.password, user.password_hash):
        rate_limit.record_failure("reauth", _client_ip(request))
        log_action(
            db,
            actor=str(user.id),
            action="auth.reauth.fail",
            target=str(user.id),
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    rate_limit.reset("reauth", _client_ip(request))
    request.session["reauth_at"] = time.time()
    request.session["reauth_method"] = "password"
    log_action(
        db,
        actor=str(user.id),
        action="auth.reauth.success",
        target=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "ok": True,
        "method": "password",
        "verified_at": request.session["reauth_at"],
    }


@router.get("/step-up/status")
def step_up_status(request: Request, _: User = Depends(current_user)):
    verified_at = request.session.get("reauth_at") or request.session.get("login_at")
    try:
        age_seconds = max(0, time.time() - float(str(verified_at)))
    except (TypeError, ValueError):
        age_seconds = None
    return {
        "method": request.session.get("reauth_method", "password"),
        "verified_at": verified_at,
        "age_seconds": age_seconds,
        "standard_valid": age_seconds is not None and age_seconds <= settings_mod.settings.recent_auth_timeout_seconds,
        "critical_valid": age_seconds is not None and age_seconds <= settings_mod.settings.critical_auth_timeout_seconds,
    }


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db_dep)):
    uid = request.session.get("user_id")
    request.session.clear()
    if uid:
        log_action(db, actor=str(uid), action="auth.logout")
        db.commit()
    return {"ok": True}


@router.post("/logout-all")
def logout_all(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
    _: None = Depends(require_recent_auth),
):
    user.session_revoked_at = datetime.fromtimestamp(time.time(), UTC)
    log_action(
        db,
        actor=str(user.id),
        action="auth.logout_all",
        target=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    request.session.clear()
    return {"ok": True}


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


@router.post("/change-password")
def change_password(
    req: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    _enforce_rate_limit("reauth", request)
    if not verify_password(req.current_password, user.password_hash):
        rate_limit.record_failure("reauth", _client_ip(request))
        log_action(
            db, actor=str(user.id), action="auth.password_change.denied",
            target=str(user.id), source_ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid current password")
    rate_limit.reset("reauth", _client_ip(request))
    user.password_hash = hash_password(req.new_password)
    user.session_revoked_at = datetime.now(UTC)
    log_action(
        db, actor=str(user.id), action="auth.password_change.success",
        target=str(user.id), source_ip=request.client.host if request.client else None,
    )
    db.commit()
    request.session.clear()
    return {"ok": True, "sessions_revoked": True}


@router.get("/me", response_model=LoginResponse)
def me(user: User = Depends(current_user)):
    return LoginResponse(display_name=user.display_name, role=user.role)


class RecoveryResetRequest(BaseModel):
    recovery_code: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=10, max_length=256)


@router.post("/recovery-reset")
def recovery_reset(req: RecoveryResetRequest, request: Request, db: Session = Depends(get_db_dep)):
    _enforce_rate_limit("recovery", request)
    user = db.query(User).filter(User.role == "admin").first()
    if user is None:
        raise HTTPException(status_code=400, detail="Setup not complete")
    if not verify_recovery_code(req.recovery_code, user.recovery_hash):
        rate_limit.record_failure("recovery", _client_ip(request))
        log_action(
            db, actor="anonymous", action="auth.recovery_reset.fail",
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid recovery code")
    rate_limit.reset("recovery", _client_ip(request))
    user.password_hash = hash_password(req.new_password)
    # A recovery reset is an account-compromise boundary.  Rotating only the
    # password would leave every previously signed browser session valid until
    # its normal expiry, including the session that prompted the reset.
    user.session_revoked_at = datetime.fromtimestamp(time.time(), UTC)
    log_action(
        db, actor=str(user.id), action="auth.recovery_reset.success",
        target=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    request.session.clear()
    return {"ok": True}


class SetupRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    recovery_code: str = Field(min_length=1, max_length=512)
    setup_token: str = Field(min_length=1, max_length=256)


@router.post("/setup")
def setup(req: SetupRequest, request: Request, db: Session = Depends(get_db_dep)):
    """Create the first admin user.

    The client must have already received a recovery code from /setup/recovery
    and is now confirming both. We accept the recovery code text and hash it
    server-side so the parent has truly written it down.
    """
    try:
        begin_immediate_if_sqlite(db)
        if not verify_setup_token(req.setup_token):
            raise HTTPException(status_code=401, detail="Invalid or expired setup token")
        existing = db.query(User).filter(User.role == "admin").first()
        if existing is not None:
            raise HTTPException(status_code=400, detail="Already set up")
    except HTTPException:
        db.rollback()
        raise
    user = User(
        display_name=req.display_name,
        password_hash=hash_password(req.password),
        recovery_hash=hash_recovery_code(req.recovery_code),
        role="admin",
    )
    try:
        db.add(user)
        db.flush()
        log_action(
            db, actor=str(user.id), action="setup.complete",
            target=str(user.id),
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        consume_setup_token()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Already set up") from None
    _mark_session_authenticated(request, user)
    return {"ok": True, "user_id": user.id}
