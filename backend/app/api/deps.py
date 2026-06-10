"""Shared FastAPI dependencies (auth + db)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import Device, User
from app.db.session import get_db
from app.services.parent_auth import verify_password


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
    """Authenticate a device via Authorization: Bearer <token>."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    # Find device whose token_hash verifies against this token.
    # Linear scan is OK for family-scale deployments.
    devices = db.query(Device).filter(Device.token_hash.isnot(None), Device.paired.is_(True)).all()
    for device in devices:
        if device.token_hash and verify_password(token, device.token_hash):
            return device
    raise HTTPException(status_code=401, detail="Invalid device token")
