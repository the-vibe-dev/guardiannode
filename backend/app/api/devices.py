"""Device management + pairing endpoints."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ulid import ULID

from app.api.deps import current_device, current_user, get_db_dep
from app.db.models import Device, User
from app.services import pairing as pairing_svc, rate_limit
from app.services.audit import log_action
from app.services.parent_auth import hash_password

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceDTO(BaseModel):
    device_id: str
    hostname: str
    platform: str
    agent_version: str
    paired: bool
    status: str
    created_at: datetime
    last_seen: datetime | None
    paused_until: datetime | None
    profile_id: str | None


def _to_dto(d: Device) -> DeviceDTO:
    return DeviceDTO(
        device_id=d.device_id,
        hostname=d.hostname,
        platform=d.platform,
        agent_version=d.agent_version,
        paired=d.paired,
        status=d.status,
        created_at=d.created_at,
        last_seen=d.last_seen,
        paused_until=d.paused_until,
        profile_id=d.profile_id,
    )


class AssignProfileRequest(BaseModel):
    profile_id: str | None  # null clears the assignment


@router.patch("/{device_id}/profile", response_model=DeviceDTO)
def assign_profile(
    device_id: str,
    req: AssignProfileRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    """Assign (or clear) the child profile a device belongs to. Frames from this
    device are then tagged with the profile so its watch phrases/age apply."""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if req.profile_id:
        from app.db.models import ChildProfile
        if db.get(ChildProfile, req.profile_id) is None:
            raise HTTPException(status_code=400, detail="Profile not found")
    device.profile_id = req.profile_id
    log_action(
        db, actor=str(user.id), action="device.assign_profile",
        target=device_id, details={"profile_id": req.profile_id},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return _to_dto(device)


@router.get("", response_model=list[DeviceDTO])
def list_devices(
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    rows = db.query(Device).order_by(Device.created_at.desc()).all()
    return [_to_dto(d) for d in rows]


class PairStartRequest(BaseModel):
    pass


class PairStartResponse(BaseModel):
    code: str
    expires_at: datetime


@router.post("/pair/start", response_model=PairStartResponse)
def pair_start(
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    code, expires_at = pairing_svc.issue(db)
    log_action(
        db, actor=str(user.id), action="device.pair.issue",
        details={"expires_at": expires_at.isoformat()},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return PairStartResponse(code=code, expires_at=expires_at)


class PairCompleteRequest(BaseModel):
    code: str = Field(default="", max_length=8)
    hostname: str = Field(max_length=256)
    platform: str = "windows"
    agent_version: str = "0.1.0"
    # All-in-one installs: the agent and backend share the machine, and no
    # parent account exists yet to issue a code. Loopback-only, first-device-only.
    local_bootstrap: bool = False


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class PairCompleteResponse(BaseModel):
    device_id: str
    device_token: str


@router.post("/pair/complete", response_model=PairCompleteResponse)
def pair_complete(
    req: PairCompleteRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
):
    client_ip = request.client.host if request.client else "unknown"
    blocked, retry_after = rate_limit.is_blocked("pairing", client_ip)
    if blocked:
        raise HTTPException(
            status_code=429,
            detail="Too many failed pairing attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if req.local_bootstrap:
        # No code needed for the very first device pairing from this machine
        # itself: nothing else can reach loopback, and once any device is
        # paired this path closes permanently.
        if client_ip not in _LOOPBACK_HOSTS:
            rate_limit.record_failure("pairing", client_ip)
            raise HTTPException(status_code=400, detail="Local bootstrap is loopback-only")
        if db.query(Device).filter(Device.paired.is_(True)).count() > 0:
            rate_limit.record_failure("pairing", client_ip)
            raise HTTPException(status_code=400, detail="Local bootstrap unavailable: a device is already paired")
    elif not pairing_svc.verify_and_consume(db, req.code.strip()):
        rate_limit.record_failure("pairing", client_ip)
        log_action(
            db, actor="anonymous", action="device.pair.fail",
            source_ip=client_ip,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")
    rate_limit.reset("pairing", client_ip)

    device_id = str(ULID())
    token = secrets.token_urlsafe(32)
    device = Device(
        device_id=device_id,
        hostname=req.hostname,
        platform=req.platform,
        agent_version=req.agent_version,
        token_hash=hash_password(token),
        paired=True,
        status="online",
        last_seen=datetime.now(timezone.utc),
    )
    db.add(device)
    log_action(
        db, actor=device_id, action="device.pair.complete",
        target=device_id,
        details={
            "hostname": req.hostname,
            "platform": req.platform,
            "local_bootstrap": req.local_bootstrap,
        },
        source_ip=client_ip,
    )
    db.commit()
    return PairCompleteResponse(device_id=device_id, device_token=token)


@router.get("/capture-config")
def capture_config(
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    """Capture knobs (cadence, change sensitivity, scope) derived from the
    child's policy. The agent polls this so a parent can tighten or loosen
    monitoring from the dashboard without touching the kid's PC."""
    from app.db.models import ChildProfile
    from app.services import profile_policy
    prof = db.get(ChildProfile, device.profile_id) if device.profile_id else None
    policy = (prof.alert_policy or {}) if prof is not None else {}
    age = prof.age_group if prof is not None else "10_13"
    cfg = profile_policy.capture_settings(policy, age)
    cfg["paused"] = device.paused_until is not None
    return cfg


class HeartbeatRequest(BaseModel):
    queued_frames: int = Field(default=0, ge=0, le=10000)
    agent_version: str | None = None


@router.post("/heartbeat")
def heartbeat(
    req: HeartbeatRequest,
    db: Session = Depends(get_db_dep),
    device: Device = Depends(current_device),
):
    """Agent liveness + upload-backlog report (shown in the pipeline widget)."""
    from app.services import pipeline_metrics
    device.last_seen = datetime.now(timezone.utc)
    if device.status not in ("paused", "disabled"):
        device.status = "online"
    if req.agent_version:
        device.agent_version = req.agent_version
    pipeline_metrics.record_agent_queue(device.device_id, device.hostname, req.queued_frames)
    db.commit()
    return {"ok": True, "paused_until": device.paused_until}


class PauseRequest(BaseModel):
    duration_seconds: int = Field(ge=1, le=86400)


@router.post("/{device_id}/pause")
def pause_device(
    device_id: str,
    req: PauseRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    until = datetime.now(timezone.utc).timestamp() + req.duration_seconds
    device.paused_until = datetime.fromtimestamp(until, tz=timezone.utc)
    device.status = "paused"
    log_action(
        db, actor=str(user.id), action="device.pause",
        target=device_id,
        details={"duration_seconds": req.duration_seconds},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True, "paused_until": device.paused_until}


@router.post("/{device_id}/resume")
def resume_device(
    device_id: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.paused_until = None
    device.status = "online"
    log_action(
        db, actor=str(user.id), action="device.resume",
        target=device_id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True}


@router.delete("/{device_id}")
def revoke_device(
    device_id: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.paired = False
    device.token_hash = None
    device.status = "disabled"
    log_action(
        db, actor=str(user.id), action="device.revoke",
        target=device_id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True}
