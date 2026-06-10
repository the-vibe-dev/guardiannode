"""Policy endpoints (per-profile)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ulid import ULID

from app.api.deps import current_user, get_db_dep
from app.db.models import Policy, User
from app.services.audit import log_action

router = APIRouter(prefix="/policies", tags=["policies"])


DEFAULT_POLICY_CONFIG = {
    "monitored_apps": [
        "Roblox.exe", "Discord.exe", "chrome.exe", "msedge.exe", "firefox.exe",
        "brave.exe", "outlook.exe", "Teams.exe", "Steam.exe", "EpicGamesLauncher.exe",
        "MinecraftLauncher.exe", "javaw.exe",
    ],
    "monitored_domains": [
        "mail.google.com", "outlook.live.com", "outlook.office.com", "discord.com",
        "roblox.com", "tiktok.com",
    ],
    "capture": {
        "scope": "monitored_window",
        "full_screen_opt_in": False,
        "cadence_seconds": 5,
    },
    "severity_thresholds": {"alert_at": "medium", "notify_at": "high"},
    "schedule": {"enabled": False, "windows": []},
    "enforcement": {
        "on_critical": ["notify_parent"],
        "on_high": ["notify_parent"],
        "on_medium": ["notify_parent_digest"],
        "on_low": ["log_only"],
    },
}


class PolicyDTO(BaseModel):
    policy_id: str
    profile_id: str
    config: dict


@router.get("", response_model=list[PolicyDTO])
def list_policies(db: Session = Depends(get_db_dep), _: User = Depends(current_user)):
    rows = db.query(Policy).all()
    return [PolicyDTO(policy_id=p.policy_id, profile_id=p.profile_id, config=p.config_json) for p in rows]


class CreatePolicyRequest(BaseModel):
    profile_id: str
    config: dict


class EffectivePolicyUpdateRequest(BaseModel):
    config: dict


@router.post("", response_model=PolicyDTO)
def create_policy(
    req: CreatePolicyRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    p = Policy(policy_id=str(ULID()), profile_id=req.profile_id, config_json=req.config)
    db.add(p)
    log_action(db, actor=str(user.id), action="policy.create", target=p.policy_id)
    db.commit()
    return PolicyDTO(policy_id=p.policy_id, profile_id=p.profile_id, config=p.config_json)


def _effective_policy(db: Session, profile_id: str) -> Policy:
    row = (
        db.query(Policy)
        .filter(Policy.profile_id == profile_id)
        .order_by(Policy.updated_at.desc())
        .first()
    )
    if row is not None:
        return row
    row = Policy(policy_id=str(ULID()), profile_id=profile_id, config_json=dict(DEFAULT_POLICY_CONFIG))
    db.add(row)
    db.flush()
    return row


@router.get("/{profile_id}/effective", response_model=PolicyDTO)
def get_effective_policy(
    profile_id: str,
    db: Session = Depends(get_db_dep),
    _: User = Depends(current_user),
):
    p = _effective_policy(db, profile_id)
    db.commit()
    return PolicyDTO(policy_id=p.policy_id, profile_id=p.profile_id, config=p.config_json)


@router.patch("/{profile_id}/effective", response_model=PolicyDTO)
def update_effective_policy(
    profile_id: str,
    req: EffectivePolicyUpdateRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    p = _effective_policy(db, profile_id)
    p.config_json = req.config
    log_action(db, actor=str(user.id), action="policy.effective.update", target=p.policy_id)
    db.commit()
    return PolicyDTO(policy_id=p.policy_id, profile_id=p.profile_id, config=p.config_json)


class UpdatePolicyRequest(BaseModel):
    config: dict


@router.patch("/{policy_id}", response_model=PolicyDTO)
def update_policy(
    policy_id: str,
    req: UpdatePolicyRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    p = db.get(Policy, policy_id)
    if p is None:
        raise HTTPException(404, "Policy not found")
    p.config_json = req.config
    log_action(db, actor=str(user.id), action="policy.update", target=policy_id)
    db.commit()
    return PolicyDTO(policy_id=p.policy_id, profile_id=p.profile_id, config=p.config_json)
