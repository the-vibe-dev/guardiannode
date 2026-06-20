"""Ingest pipeline: redact → store encrypted → classify → maybe alert."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import Device, Event, RiskResult
from app.services import classifier, encryption, redaction
from app.services.audit import log_action
from app.services.profile_resolution import resolve_profile

log = logging.getLogger(__name__)


def _ulid() -> str:
    return str(ULID())


async def ingest_event(
    session: Session,
    *,
    payload: dict[str, Any],
    device_id: str,
    source_ip: str | None = None,
) -> dict[str, Any]:
    """Ingest a single text event payload (generic text-ingest API).

    Returns a small dict with event_id, risk_id (if classified), and severity.
    """
    text = payload.get("redacted_text") or ""
    if text:
        red = redaction.redact(text)
        text = red.redacted_text
        red_summary = red.summary
    else:
        red_summary = {}

    event_id = payload.get("event_id") or _ulid()
    ts_str = payload.get("timestamp")
    try:
        timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)
    except Exception:
        timestamp = datetime.now(timezone.utc)

    metadata = dict(payload.get("metadata") or {})
    metadata.setdefault("capture_scope", payload.get("capture_scope", "browser_dom"))
    for key in ("policy_id", "policy_version", "collector_version"):
        if payload.get(key) is not None:
            metadata[key] = payload.get(key)
    if red_summary:
        metadata["redaction"] = red_summary
        metadata["redaction_summary"] = red_summary

    device = session.get(Device, device_id)

    # Resolve the child profile the same way screenshot ingest does. The
    # backend assignment is authoritative; device payload profile/age fields are
    # legacy hints only and may not select another child's policy.
    resolved = resolve_profile(
        session,
        device=device,
        payload_profile_id=payload.get("profile_id"),
        payload_age_group=payload.get("age_group") or payload.get("_age_group"),
    )

    event = Event(
        event_id=event_id,
        device_id=device_id,
        profile_id=resolved.profile_id,
        source_type=payload.get("source_type", "ocr"),
        app_name=payload.get("app_name"),
        window_title=payload.get("window_title"),
        url=payload.get("url"),
        timestamp=timestamp,
        redacted_text_enc=encryption.encrypt_text(text) if text else None,
        evidence_type=payload.get("evidence_type", "visible_text"),
        screenshot_blob_id=payload.get("screenshot_blob_id"),
        image_blob_id=payload.get("image_blob_id"),
        event_metadata=metadata,
        received_at=datetime.now(timezone.utc),
        key_version=encryption.current_key_version(),
    )
    session.add(event)

    # Update device last_seen
    if device is not None:
        device.last_seen = datetime.now(timezone.utc)
        device.status = "online"

    # Classify
    cls_result = await classifier.classify_text(
        redacted_text=text,
        app_name=payload.get("app_name"),
        source_type=payload.get("source_type", "ocr"),
        age_group=resolved.age_group,
        timestamp=timestamp.isoformat(),
        url=payload.get("url"),
        custom_phrases=resolved.custom_phrases,
    )

    risk_id = _ulid()
    rr = RiskResult(
        risk_id=risk_id,
        event_id=event_id,
        risk_level=cls_result["risk_level"],
        score=cls_result["score"],
        categories=cls_result["categories"],
        summary=cls_result["summary"],
        evidence=cls_result["evidence"],
        recommended_action=cls_result["recommended_action"],
        model=cls_result["model"],
        rules_triggered=cls_result["rules_triggered"],
        confidence=cls_result["confidence"],
        false_positive_notes=cls_result["false_positive_notes"],
        prompt_version=cls_result["prompt_version"],
        rules_version=cls_result["rules_version"],
        classifier_status=cls_result.get("status", "ok"),
    )
    session.add(rr)

    severity = cls_result["risk_level"]
    alert_id: str | None = None
    from app.services import profile_policy
    if resolved.profile is not None:
        pol = profile_policy.normalize(resolved.profile.alert_policy or {}, resolved.age_group)
    else:
        pol = profile_policy.default_policy_for_age(resolved.age_group)
    decision = profile_policy.decide(pol, severity, cls_result["categories"]) if severity != "none" else profile_policy.Decision(False, False, "no_risk")
    if decision.create_alert:
        from app.services.alert_dedup import upsert_alert
        alert_id, _created = upsert_alert(
            session,
            risk_id=risk_id,
            device_id=device_id,
            profile_id=resolved.profile_id,
            severity=severity,
            categories=cls_result["categories"],
            source="text_event",
            source_ip=source_ip,
            notify=decision.notify,
            risk_summary=cls_result.get("summary", ""),
        )

    return {
        "event_id": event_id,
        "risk_id": risk_id,
        "alert_id": alert_id,
        "risk_level": severity,
        "score": cls_result["score"],
        "categories": cls_result["categories"],
    }
