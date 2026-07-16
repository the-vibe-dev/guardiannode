"""Authoritative incident loading and deterministic outbound minimization."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.db.models import Alert, ChildProfile, Device, Event, RiskResult
from app.guardian_review_models import (
    REDACTION_VERSION,
    GuardianReviewContext,
    GuardianReviewOutboundPayload,
)
from app.services import encryption, redaction

_EMAIL = re.compile(r"(?<![\w.+-])[\w.%+-]{1,64}@[\w.-]{1,253}\.[^\W\d_]{2,63}\b", re.I)
_OBFUSCATED_EMAIL = re.compile(
    r"(?<!\w)([\w.%+-]{1,64})\s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\s+at\s+)\s*"
    r"([\w-]{1,63}(?:\s*(?:\.|\[\s*dot\s*\]|\(\s*dot\s*\)|\s+dot\s+)\s*[\w-]{1,63})*"
    r"\s*(?:\.|\[\s*dot\s*\]|\(\s*dot\s*\)|\s+dot\s+)\s*[^\W\d_]{2,63})",
    re.I,
)
_PHONE_CANDIDATE = re.compile(r"(?<!\w)(?:\+?\d[\s().\-/]*){7,15}(?!\w)")
_URL = re.compile(r"(?i)(?<!\w)(?:(?:https?|hxxps?)://|www\.)[^\s<>\"']+")
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HANDLE = re.compile(r"(?<!\w)@[\w][\w.\-]{1,63}", re.UNICODE)
_WINDOWS_PATH = re.compile(r"(?i)(?<!\w)[a-z]:\\(?:[^\\\r\n]+)")
_UNC_PATH = re.compile(r"\\\\[^\\\s]+\\[^\r\n]+")
_POSIX_PATH = re.compile(r"(?<!\w)/(?:home|users|mnt|var|tmp|opt|srv|data)/(?:[^\s\r\n]+)", re.I)
_FILE_URI = re.compile(r"(?i)\bfile:(?://)?[^\s<>\"']+")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
_WINDOWS_SID = re.compile(r"\bS-1-(?:\d+-){2,14}\d+\b", re.I)
_LABELED_ACCOUNT_ID = re.compile(
    r"(?i)\b(?:account|acct|user|profile|member)[ _-]?(?:id|number)\s*[:=#-]?\s*[\w.-]{4,128}\b"
)
_LABELED_USERNAME = re.compile(
    r"(?i)\b(?:user(?:name)?|screen[ _-]?name|handle|login)\s*[:=#-]\s*[\w.-]{2,64}\b"
)
_COORDINATES = re.compile(r"(?<!\d)[+-]?(?:\d{1,2}|1[0-7]\d)\.\d{3,}\s*[,;/ ]\s*[+-]?(?:\d{1,2}|1[0-7]\d)\.\d{3,}(?!\d)")
_STREET_ADDRESS = re.compile(
    r"\b\d{1,6}\s+(?:[^\W_]+[ .'-]+){0,5}(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|boulevard|blvd|way|place|pl)\b",
    re.I,
)
_POSTAL_LOCATION = re.compile(
    r"(?i)\b(?:[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,2},?\s+)?(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\s+\d{5}(?:-\d{4})?\b"
)

_URL_RELEVANT_CATEGORIES = {"phishing", "scam", "unknown_link"}
_KNOWN_CATEGORIES = {
    "none", "self_harm", "grooming", "sexual_content", "sexual_exploitation",
    "child_sexual_content", "nudity", "bullying", "threat", "scam", "phishing",
    "private_info", "private_info_request", "private_info_visible", "off_platform_contact",
    "secrecy_request", "drugs", "weapons", "gore", "hate_symbol", "dangerous_challenge",
    "profanity", "unknown_link", "custom_watch", "monitoring_gap", "unknown",
}
_MAX_EVIDENCE_ITEMS = 8
_MAX_EVIDENCE_ITEM_CHARS = 800
_MAX_EVIDENCE_TOTAL_CHARS = 4800
_MAX_OUTBOUND_CHARS = 12_000


class InvalidIncidentError(ValueError):
    pass


@dataclass(frozen=True)
class MinimizedIncident:
    alert: Alert
    payload: dict[str, Any]
    digest: str
    fingerprint: str
    redactions: list[str]
    information_categories: list[str]


@dataclass
class _PrivacyRedactor:
    alert_id: str
    profile: ChildProfile | None
    device: Device | None
    url_destination_relevant: bool
    counts: dict[str, int] = field(default_factory=dict)

    def _count(self, tag: str, count: int = 1) -> None:
        self.counts[tag] = self.counts.get(tag, 0) + count

    def placeholder(self, tag: str, raw: str) -> str:
        normalized = unicodedata.normalize("NFKC", raw).strip().casefold()
        material = f"{REDACTION_VERSION}\0{self.alert_id}\0{tag}\0{normalized}".encode()
        suffix = hmac.new(encryption.get_master_key(), material, hashlib.sha256).hexdigest()[:8].upper()
        self._count(tag)
        return f"[{tag.upper()}_{suffix}]"

    def replace_pattern(self, pattern: re.Pattern[str], tag: str, value: str) -> str:
        return pattern.sub(lambda match: self.placeholder(tag, match.group(0)), value)

    def clean(self, value: str | None, *, limit: int) -> str | None:
        if not value:
            return None
        value = unicodedata.normalize("NFKC", value[: max(limit * 4, limit)])
        value = "".join(ch for ch in value if unicodedata.category(ch) != "Cf")
        value = re.sub(r"(?i)\b(hxxps?|https?)\s*\[\s*:\s*\]\s*//", r"\1://", value)
        secret_result = redaction.redact(value)
        value = secret_result.redacted_text
        for name, count in secret_result.summary.items():
            self._count(name, count)

        known_terms: list[tuple[str, str]] = []
        if self.profile:
            known_terms.append((str(self.profile.display_name or ""), "child"))
            known_terms.extend((str(term), "profile_term") for term in (self.profile.custom_watch_phrases or []))
        if self.device:
            known_terms.append((str(self.device.hostname or ""), "device"))
        for term, tag in sorted(known_terms, key=lambda item: len(item[0]), reverse=True):
            term = term.strip()
            if len(term) < 2:
                continue
            replacement = "[CHILD]" if tag == "child" else "[DEVICE]" if tag == "device" else self.placeholder(tag, term)
            value, count = re.subn(re.escape(term), replacement, value, flags=re.I)
            if count:
                self._count(tag, count if tag in {"child", "device"} else max(0, count - 1))

        value = _OBFUSCATED_EMAIL.sub(lambda match: self.placeholder("email", match.group(0)), value)
        value = self.replace_pattern(_EMAIL, "email", value)
        value = self.replace_pattern(_FILE_URI, "path", value)
        value = self.replace_pattern(_WINDOWS_PATH, "path", value)
        value = self.replace_pattern(_UNC_PATH, "path", value)
        value = self.replace_pattern(_POSIX_PATH, "path", value)
        value = _URL.sub(self._replace_url, value)
        value = self.replace_pattern(_IP, "ip", value)
        value = self.replace_pattern(_WINDOWS_SID, "account_id", value)
        value = self.replace_pattern(_UUID, "account_id", value)
        value = self.replace_pattern(_LABELED_ACCOUNT_ID, "account_id", value)
        value = self.replace_pattern(_LABELED_USERNAME, "username", value)
        value = self.replace_pattern(_HANDLE, "handle", value)
        value = self.replace_pattern(_COORDINATES, "location", value)
        value = _PHONE_CANDIDATE.sub(self._replace_phone, value)
        value = self.replace_pattern(_STREET_ADDRESS, "address", value)
        value = self.replace_pattern(_POSTAL_LOCATION, "location", value)
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value).strip()
        return value[:limit].rstrip() or None

    def _replace_phone(self, match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 7 <= len(digits) <= 15 and (len(digits) >= 10 or any(ch in raw for ch in "+().-/ ")):
            return self.placeholder("phone", raw)
        return raw

    def _replace_url(self, match: re.Match[str]) -> str:
        raw = match.group(0)
        normalized = re.sub(r"(?i)^hxxp", "http", raw)
        if normalized.lower().startswith("www."):
            normalized = "https://" + normalized
        try:
            hostname = (urlsplit(normalized).hostname or "").strip(".").lower()
            hostname = hostname.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            hostname = ""
        if self.url_destination_relevant and hostname:
            self._count("url")
            return f"[URL_DOMAIN:{hostname[:253]}]"
        return self.placeholder("url", raw)


def minimize_text(
    value: str,
    *,
    profile: ChildProfile | None,
    alert_id: str = "standalone",
    device: Device | None = None,
    url_destination_relevant: bool = False,
) -> tuple[str, dict[str, int]]:
    """Compatibility wrapper used by focused tests and callers outside the workflow."""
    minimizer = _PrivacyRedactor(alert_id, profile, device, url_destination_relevant)
    return minimizer.clean(value, limit=8000) or "", dict(minimizer.counts)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _evidence_items(risk: RiskResult, event: Event) -> list[tuple[str, str, bool]]:
    items: list[tuple[str, str, bool]] = []
    for index, item in enumerate(risk.evidence or []):
        text = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
        if text.strip():
            items.append((f"risk:{index}", text, True))
    if event.redacted_text_enc:
        try:
            text = encryption.decrypt_text(event.redacted_text_enc)
        except Exception:
            text = ""
        if text.strip():
            items.append(("event:text", _bounded_event_context(text, risk), not items))
    return items


def _bounded_event_context(text: str, risk: RiskResult) -> str:
    folded = text.casefold()
    for item in risk.evidence or []:
        if not isinstance(item, str):
            continue
        anchor = item.strip()[:120]
        if len(anchor) < 4:
            continue
        index = folded.find(anchor.casefold())
        if index >= 0:
            return text[max(0, index - 200) : index + len(anchor) + 400]
    return text[:800]


def _safe_rule(value: Any) -> str | None:
    normalized = re.sub(r"[^A-Za-z0-9:_-]+", "_", str(value))[:128].strip("_")
    return normalized or None


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
    device = db.get(Device, event.device_id) if event.device_id else None
    evidence = _evidence_items(risk, event)
    known_ids = {item_id for item_id, _, _ in evidence}
    if not context.include_evidence:
        selected: set[str] = set()
    elif context.selected_evidence_ids:
        selected = set(context.selected_evidence_ids)
    else:
        selected = {item_id for item_id, _, selected_by_detector in evidence if selected_by_detector}
    if not selected.issubset(known_ids):
        raise InvalidIncidentError("Selected evidence does not belong to the incident")

    categories = [str(value) for value in (risk.categories or []) if str(value) in _KNOWN_CATEGORIES][:_MAX_EVIDENCE_ITEMS + 2]
    if not categories:
        categories = ["unknown"]
    minimizer = _PrivacyRedactor(
        alert_id=alert_id,
        profile=profile,
        device=device,
        url_destination_relevant=bool(set(categories) & _URL_RELEVANT_CATEGORIES),
    )

    minimized_evidence: list[dict[str, str]] = []
    seen_text: set[str] = set()
    evidence_characters = 0
    for evidence_id, text, _selected_by_detector in evidence:
        if evidence_id not in selected or len(minimized_evidence) >= _MAX_EVIDENCE_ITEMS:
            continue
        cleaned = minimizer.clean(text, limit=_MAX_EVIDENCE_ITEM_CHARS)
        if not cleaned:
            continue
        identity = re.sub(r"\s+", " ", cleaned).casefold()
        if identity in seen_text:
            continue
        remaining = _MAX_EVIDENCE_TOTAL_CHARS - evidence_characters
        if remaining <= 0:
            break
        cleaned = cleaned[:remaining].rstrip()
        if not cleaned:
            break
        seen_text.add(identity)
        minimized_evidence.append({"evidence_id": f"evidence_{len(minimized_evidence) + 1}", "text": cleaned})
        evidence_characters += len(cleaned)

    rules_triggered = [rule for value in (risk.rules_triggered or []) if (rule := _safe_rule(value))][:20]
    payload_model = GuardianReviewOutboundPayload.model_validate({
        "local_detector_findings": {
            "severity": alert.severity if alert.severity in {"none", "low", "medium", "high", "critical"} else "none",
            "categories": categories,
            "summary": minimizer.clean(risk.summary, limit=800) or "No local summary available.",
            "rules_triggered": rules_triggered,
        },
        "minimized_evidence": minimized_evidence,
        "approximate_child_age_group": (
            profile.age_group if context.include_age_group and profile and profile.age_group in {"under_10", "10_13", "14_17"}
            else "unknown" if context.include_age_group else None
        ),
        "known_relationship_context": context.relationship_context,
        "behavior_repeated": context.repeated_behavior,
        "parent_believes_immediate_danger": context.parent_believes_immediate_danger,
        "parent_goal": context.parent_goal,
        "parent_goal_details": minimizer.clean(context.parent_goal_details, limit=300),
        "parent_supplied_context": minimizer.clean(context.parent_context, limit=1500),
    })
    payload = payload_model.model_dump(mode="json", exclude_none=True)
    if len(_canonical(payload).decode("utf-8")) > _MAX_OUTBOUND_CHARS:
        raise InvalidIncidentError("Minimized incident exceeds the outbound size limit")
    information_categories = ["local_detector_findings"]
    if minimized_evidence:
        information_categories.append("minimized_evidence")
    if payload.get("approximate_child_age_group") is not None:
        information_categories.append("approximate_age_group")
    information_categories.extend(["relationship_context", "repeat_context", "immediate_danger_belief", "parent_goal"])
    if payload.get("parent_goal_details"):
        information_categories.append("parent_goal_details")
    if payload.get("parent_supplied_context"):
        information_categories.append("parent_supplied_context")

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
        "redaction_version": REDACTION_VERSION,
        "provider": provider,
        "model": model,
    }
    return MinimizedIncident(
        alert=alert,
        payload=payload,
        digest=hashlib.sha256(_canonical(digest_material)).hexdigest(),
        fingerprint=fingerprint,
        redactions=sorted(minimizer.counts),
        information_categories=information_categories,
    )
