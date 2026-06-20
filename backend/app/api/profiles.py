"""Child profile management."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ulid import ULID

from app.api.deps import current_user, get_db_dep
from app.db.models import ChildProfile, User
from app.services import profile_policy
from app.services.audit import log_action

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileDTO(BaseModel):
    profile_id: str
    display_name: str
    age_group: str
    created_at: datetime
    notes: str | None
    custom_watch_phrases: list[str] = []
    # Normalized (age-default-filled) policy so the UI always has a full object.
    alert_policy: dict = {}


def _to_dto(p: ChildProfile) -> ProfileDTO:
    return ProfileDTO(
        profile_id=p.profile_id,
        display_name=p.display_name,
        age_group=p.age_group,
        created_at=p.created_at,
        notes=p.notes,
        custom_watch_phrases=list(p.custom_watch_phrases or []),
        alert_policy=profile_policy.normalize(p.alert_policy or {}, p.age_group),
    )


@router.get("", response_model=list[ProfileDTO])
def list_profiles(db: Session = Depends(get_db_dep), _: User = Depends(current_user)):
    return [_to_dto(p) for p in db.query(ChildProfile).order_by(ChildProfile.created_at).all()]


def _clean_phrases(phrases: list[str] | None) -> list[str]:
    """Trim, dedupe, drop empties, bound length. Phrases are case-insensitive
    on match, so we keep the original casing for display only.
    """
    if not phrases:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in phrases:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s or len(s) > 200:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= 200:
            break
    return out


class CreateProfileRequest(BaseModel):
    display_name: str = Field(max_length=128)
    age_group: str = Field(pattern="^(under_10|10_13|14_17)$")
    notes: str | None = Field(default=None, max_length=2048)
    custom_watch_phrases: list[str] = Field(default_factory=list)


@router.post("", response_model=ProfileDTO)
def create_profile(
    req: CreateProfileRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    p = ChildProfile(
        profile_id=str(ULID()),
        display_name=req.display_name,
        age_group=req.age_group,
        notes=req.notes,
        custom_watch_phrases=_clean_phrases(req.custom_watch_phrases),
        # Seed with the age-appropriate default policy; parent tunes it after.
        alert_policy=profile_policy.default_policy_for_age(req.age_group),
    )
    db.add(p)
    log_action(db, actor=str(user.id), action="profile.create", target=p.profile_id)
    db.commit()
    return _to_dto(p)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    age_group: str | None = Field(default=None, pattern="^(under_10|10_13|14_17)$")
    notes: str | None = Field(default=None, max_length=2048)
    custom_watch_phrases: list[str] | None = Field(default=None)
    alert_policy: dict | None = None
    # If true, replace the policy with the default preset for the (new) age group.
    reset_policy_to_age_default: bool = False


@router.patch("/{profile_id}", response_model=ProfileDTO)
def update_profile(
    profile_id: str,
    req: UpdateProfileRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    p = db.get(ChildProfile, profile_id)
    if p is None:
        raise HTTPException(404, "Profile not found")
    if req.display_name is not None:
        p.display_name = req.display_name
    if req.age_group is not None:
        p.age_group = req.age_group
    if req.notes is not None:
        p.notes = req.notes
    if req.custom_watch_phrases is not None:
        p.custom_watch_phrases = _clean_phrases(req.custom_watch_phrases)
    if req.reset_policy_to_age_default:
        p.alert_policy = profile_policy.default_policy_for_age(p.age_group)
    elif req.alert_policy is not None:
        # Store the normalized policy so it's always complete/valid.
        p.alert_policy = profile_policy.normalize(req.alert_policy, p.age_group)
    log_action(db, actor=str(user.id), action="profile.update", target=profile_id)
    db.commit()
    return _to_dto(p)


class PolicyMeta(BaseModel):
    tunable_categories: list[dict]
    protected_categories: list[str]
    modes: list[str]
    severities: list[str]
    capture_levels: list[str]


@router.get("/policy/meta", response_model=PolicyMeta)
def policy_meta(_: User = Depends(current_user)):
    """Category labels + option lists so the dashboard can render the policy UI."""
    return PolicyMeta(
        tunable_categories=[{"key": k, "label": lbl} for k, lbl in profile_policy.TUNABLE_CATEGORIES],
        protected_categories=sorted(profile_policy.PROTECTED_CATEGORIES),
        modes=["alert", "monitor", "allow"],
        severities=["low", "medium", "high", "critical"],
        capture_levels=list(profile_policy.CAPTURE_LEVELS.keys()),
    )


@router.delete("/{profile_id}")
def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db_dep),
    user: User = Depends(current_user),
):
    p = db.get(ChildProfile, profile_id)
    if p is None:
        raise HTTPException(404, "Profile not found")
    db.delete(p)
    log_action(db, actor=str(user.id), action="profile.delete", target=profile_id)
    db.commit()
    return {"ok": True}
