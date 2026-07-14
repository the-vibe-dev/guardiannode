"""Authoritative incident loading and outbound minimization for Guardian Review."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Alert, ChildProfile, Event, RiskResult
from app.guardian_review_models import GuardianReviewContext
from app.services import encryption, redaction

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\w)")
_URL = re.compile(r"\bhttps?://[^\s]+", re.I)
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HANDLE = re.compile(r"(?<!\w)@[A-Za-z0-9_.-]{2,32}\b")


class InvalidIncidentError(ValueError):
    pass


@dataclass(frozen=True)
class MinimizedIncident:
    alert: Alert
    payload: dict[str, Any]
    digest: str
    fingerprint: str
    redactions: list[str]


def _replace(pattern: re.Pattern[str], tag: str, value: str, counts: dict[str, int]) -> str:
    def sub(_match: re.Match[str]) -> str:
        counts[tag] = counts.get(tag, 0) + 1
        return f"[REDACTED:{tag}]"
    return pattern.sub(sub, value)


def minimize_text(value: str, *, profile: ChildProfile | None) -> tuple[str, dict[str, int]]:
    value = value[:8000]
    counts: dict[str, int] = {}
    secret_result = redaction.redact(value)
    value = secret_result.redacted_text
    counts.update(secret_result.summary)
    for pattern, tag in ((_EMAIL, "email"), (_PHONE, "phone"), (_URL, "url"), (_IP, "ip"), (_HANDLE, "handle")):
        value = _replace(pattern, tag, value, counts)
    if profile is not None:
        sensitive_phrases = [profile.display_name, *(profile.custom_watch_phrases or [])]
        for phrase in sensitive_phrases:
            phrase = str(phrase).strip()
            if len(phrase) < 2:
                continue
            value, n = re.subn(re.escape(phrase), "[REDACTED:profile_term]", value, flags=re.I)
            if n:
                counts["profile_term"] = counts.get("profile_term", 0) + n
    return value.strip(), counts


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _evidence_items(risk: RiskResult, event: Event) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for index, item in enumerate(risk.evidence or []):
        text = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
        if text.strip():
            items.append((f"risk:{index}", text))
    if event.redacted_text_enc:
        try:
            text = encryption.decrypt_text(event.redacted_text_enc)
        except Exception:
            text = ""
        if text.strip():
            items.append(("event:text", text))
    return items


def build_minimized_incident(
    db: Session,
    *,
    alert_id: str,
    context: GuardianReviewContext,
    schema_version: str,
    prompt_version: str,
    provider: str,
    model: str,
) -> MinimizedIncident:
    alert = db.get(Alert, alert_id)
    risk = db.get(RiskResult, alert.risk_id) if alert else None
    event = db.get(Event, risk.event_id) if risk else None
    if alert is None or risk is None or event is None:
        raise InvalidIncidentError("Incident not found or incomplete")
    profile_id = alert.profile_id or event.profile_id
    profile = db.get(ChildProfile, profile_id) if profile_id else None
    evidence = _evidence_items(risk, event)
    known_ids = {item_id for item_id, _ in evidence}
    selected = set(context.selected_evidence_ids or known_ids)
    if not selected.issubset(known_ids):
        raise InvalidIncidentError("Selected evidence does not belong to the incident")

    redaction_counts: dict[str, int] = {}

    def clean(value: str | None, *, limit: int) -> str | None:
        if not value:
            return None
        cleaned, counts = minimize_text(value[:limit], profile=profile)
        for name, count in counts.items():
            redaction_counts[name] = redaction_counts.get(name, 0) + count
        return cleaned or None

    minimized_evidence = []
    for evidence_id, text in evidence:
        if evidence_id not in selected:
            continue
        minimized_evidence.append({"evidence_id": evidence_id, "text": clean(text, limit=1200) or "[empty]"})

    payload: dict[str, Any] = {
        "incident_id": alert.alert_id,
        "local_detector_findings": {
            "severity": alert.severity,
            "risk_level": risk.risk_level,
            "score": max(0, min(100, int(risk.score))),
            "categories": [str(v)[:64] for v in (risk.categories or [])[:10]],
            "summary": clean(risk.summary, limit=1200) or "No local summary available.",
            "rules_triggered": [str(v)[:128] for v in (risk.rules_triggered or [])[:20]],
            "classifier_status": risk.classifier_status,
        },
        "minimized_evidence": minimized_evidence,
        "approximate_child_age_group": profile.age_group if profile else "unknown",
        "known_relationship_context": context.relationship_context,
        "behavior_repeated": context.repeated_behavior,
        "local_repeat_count": max(1, int(alert.repeat_count or 1)),
        "parent_believes_immediate_danger": context.parent_believes_immediate_danger,
        "parent_goal": context.parent_goal,
        "parent_goal_details": clean(context.parent_goal_details, limit=500),
        "parent_supplied_context": clean(context.parent_context, limit=4000),
    }
    incident_state = {
        "alert_id": alert.alert_id,
        "risk_id": risk.risk_id,
        "event_id": event.event_id,
        "alert_last_seen": alert.last_seen_at.isoformat() if alert.last_seen_at else None,
        "repeat_count": alert.repeat_count,
        "risk_created_at": risk.created_at.isoformat(),
    }
    fingerprint = hashlib.sha256(_canonical(incident_state)).hexdigest()
    digest_material = {
        "payload": payload,
        "schema_version": schema_version,
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
    }
    return MinimizedIncident(
        alert=alert,
        payload=payload,
        digest=hashlib.sha256(_canonical(digest_material)).hexdigest(),
        fingerprint=fingerprint,
        redactions=sorted(redaction_counts),
    )
