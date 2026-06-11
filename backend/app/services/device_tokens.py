"""Device token format + verification.

Tokens issued at pairing look like::

    gn_dev_<device_id>_<random_secret>

The device id is embedded so the backend can look the device up directly and
verify exactly ONE Argon2 hash per request, instead of linearly verifying every
paired device's hash (Argon2 is deliberately expensive — a linear scan made
invalid-token requests cheap to weaponize).

Already-paired devices hold legacy opaque tokens with no embedded id; those
still fall back to the linear scan so an upgrade never un-pairs a child device.
New pairings always get the structured format.
"""
from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.db.models import Device
from app.services.parent_auth import hash_password, verify_password

TOKEN_PREFIX = "gn_dev_"


def issue_token(device_id: str) -> tuple[str, str]:
    """Create a new device token. Returns (full_token, secret_hash_for_storage)."""
    secret = secrets.token_urlsafe(32)
    return f"{TOKEN_PREFIX}{device_id}_{secret}", hash_password(secret)


def parse_token(token: str) -> tuple[str, str] | None:
    """Split a structured token into (device_id, secret); None if legacy/opaque."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    rest = token[len(TOKEN_PREFIX):]
    # device ids are ULIDs (no underscores); the secret may contain them.
    device_id, sep, secret = rest.partition("_")
    if not sep or not device_id or not secret:
        return None
    return device_id, secret


def authenticate(db: Session, token: str) -> Device | None:
    """Resolve a bearer token to a paired device, or None.

    Structured tokens cost one DB get + one Argon2 verify. Legacy tokens fall
    back to scanning paired devices (family-scale: a handful of rows).
    """
    parsed = parse_token(token)
    if parsed is not None:
        device_id, secret = parsed
        device = db.get(Device, device_id)
        if (
            device is not None
            and device.paired
            and device.token_hash
            and verify_password(secret, device.token_hash)
        ):
            return device
        return None

    # Legacy opaque token: linear scan (kept so existing pairings survive).
    devices = db.query(Device).filter(Device.token_hash.isnot(None), Device.paired.is_(True)).all()
    for device in devices:
        if device.token_hash and verify_password(token, device.token_hash):
            return device
    return None
