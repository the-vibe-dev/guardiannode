"""Authentication: login, logout, current user, password reset via recovery code."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db_dep
from app.db.models import User
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
    request.session["user_id"] = user.id
    log_action(
        db, actor=str(user.id), action="auth.login.success",
        target=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return LoginResponse(display_name=user.display_name, role=user.role)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db_dep)):
    uid = request.session.get("user_id")
    request.session.clear()
    if uid:
        log_action(db, actor=str(uid), action="auth.logout")
        db.commit()
    return {"ok": True}


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
    log_action(
        db, actor=str(user.id), action="auth.recovery_reset.success",
        target=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
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
    if not verify_setup_token(req.setup_token):
        raise HTTPException(status_code=401, detail="Invalid or expired setup token")
    existing = db.query(User).filter(User.role == "admin").first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Already set up")
    user = User(
        display_name=req.display_name,
        password_hash=hash_password(req.password),
        recovery_hash=hash_recovery_code(req.recovery_code),
        role="admin",
    )
    db.add(user)
    db.flush()
    log_action(
        db, actor=str(user.id), action="setup.complete",
        target=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    consume_setup_token()
    request.session["user_id"] = user.id
    return {"ok": True, "user_id": user.id}
