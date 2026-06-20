"""Shared child-profile resolution for every ingest path.

The authenticated device's dashboard assignment is authoritative. Device
payloads may include legacy ``profile_id`` or age fields, but paired devices
must not be able to choose another child's profile or policy.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import ChildProfile, Device
from app.services.audit import log_action

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
    device: Device | None = None,
    device_id: str | None = None,
    payload_profile_id: str | None = None,
    payload_age_group: str | None = None,
) -> ResolvedProfile:
    """Resolve the effective child profile for an authenticated device.

    ``payload_age_group`` is accepted only for API compatibility and is not
    authoritative for paired devices.
    """
    if device is None and device_id:
        device = session.get(Device, device_id)

    actor = device.device_id if device is not None else (device_id or "unknown-device")

    if payload_profile_id and (device is None or payload_profile_id != device.profile_id):
        log.warning(
            "event from device %s attempted profile override %r; using server assignment",
            actor,
            payload_profile_id,
        )
        log_action(
            session,
            actor=actor,
            action="device.profile_mismatch",
            target=payload_profile_id,
            details={
                "assigned_profile_id": device.profile_id if device is not None else None,
                "payload_profile_id": payload_profile_id,
            },
        )

    profile: ChildProfile | None = None
    if device is not None and device.profile_id:
        profile = session.get(ChildProfile, device.profile_id)
        if profile is None:
            log.warning(
                "device %s is assigned to missing profile %r; using defaults",
                device.device_id,
                device.profile_id,
            )

    if profile is not None:
        return ResolvedProfile(
            profile_id=profile.profile_id,
            profile=profile,
            age_group=profile.age_group or DEFAULT_AGE_GROUP,
            custom_phrases=list(profile.custom_watch_phrases or []),
        )

    if payload_age_group and payload_age_group != DEFAULT_AGE_GROUP:
        log.debug("ignoring device-supplied age group %r from %s", payload_age_group, actor)
    age_group = DEFAULT_AGE_GROUP
    return ResolvedProfile(profile_id=None, profile=None, age_group=age_group, custom_phrases=[])
