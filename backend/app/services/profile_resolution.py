"""Shared child-profile resolution for every ingest path.

Screenshot ingest and generic text-event ingest must resolve the child profile
the same way, or custom watch phrases and age-based policy behave
inconsistently between the two. Resolution order:

1. the payload's ``profile_id`` — but only if that profile actually exists
   (an agent cannot point events at a profile the parent never created)
2. the profile the parent assigned to the device in the dashboard
3. no profile → callers fall back to the balanced ``10_13`` age default

Returns the resolved profile id, the loaded ``ChildProfile`` (or None), the
effective age group, and the parent's custom watch phrases — everything an
ingest path needs to classify consistently.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import ChildProfile, Device

log = logging.getLogger(__name__)

DEFAULT_AGE_GROUP = "10_13"


@dataclass
class ResolvedProfile:
    profile_id: str | None
    profile: ChildProfile | None
    age_group: str
    custom_phrases: list[str] = field(default_factory=list)


def resolve_profile(
    session: Session,
    *,
    device_id: str,
    payload_profile_id: str | None = None,
    payload_age_group: str | None = None,
) -> ResolvedProfile:
    """Resolve the effective child profile for an event from ``device_id``.

    ``payload_age_group`` is only honored when no profile resolves at all
    (legacy agents that send an age group but no profile).
    """
    profile: ChildProfile | None = None

    if payload_profile_id:
        profile = session.get(ChildProfile, payload_profile_id)
        if profile is None:
            log.warning(
                "event from device %s referenced unknown profile %r; using device assignment",
                device_id, payload_profile_id,
            )

    if profile is None:
        device = session.get(Device, device_id)
        if device is not None and device.profile_id:
            profile = session.get(ChildProfile, device.profile_id)
            if profile is None:
                log.warning(
                    "device %s is assigned to missing profile %r; using defaults",
                    device_id, device.profile_id,
                )

    if profile is not None:
        return ResolvedProfile(
            profile_id=profile.profile_id,
            profile=profile,
            age_group=profile.age_group or DEFAULT_AGE_GROUP,
            custom_phrases=list(profile.custom_watch_phrases or []),
        )

    age_group = payload_age_group if payload_age_group in ("under_10", "10_13", "14_17") else DEFAULT_AGE_GROUP
    return ResolvedProfile(profile_id=None, profile=None, age_group=age_group, custom_phrases=[])
