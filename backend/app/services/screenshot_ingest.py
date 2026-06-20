"""Screenshot ingest pipeline — tiered for hardware capability.

Three tiers govern what runs per screenshot:

* **full**         — vision LLM + text LLM run in parallel. Vision LLM does OCR + visual
                     classification. Text LLM does nuanced text classification on the
                     OCR'd content. Best coverage. Requires 10+ GB VRAM total
                     (qwen2.5vl:7b + llama3.2:3b kept hot together).
* **vision_only**  — vision LLM only. Vision LLM judges both image + text. Rules engine
                     also runs on OCR text for fast deterministic catches. Requires
                     6+ GB VRAM.
* **text_only**    — Tesseract OCR + small text LLM (llama3.2:1b) on CPU. NO image-only
                     risk detection (nudity/gore/weapons). Catches all text-based risks.
                     For low-end family PCs with no GPU.

The tier is chosen by `settings.classifier_tier` (env GUARDIANNODE_CLASSIFIER_TIER).
The installer detects hardware and sets it at install time.

Blob storage threshold: severity >= medium gets an encrypted screenshot kept; below
that we discard bytes to keep disk usage low.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import ChildProfile, Device, Event, EvidenceBlob, RiskResult
from app.services import (
    classifier,
    encryption,
    image_safety,
    multimodal_risk,
    pipeline_metrics,
    risk_rules,
)
from app.services.ollama_client import OllamaClient
from app.services.profile_resolution import resolve_profile
from app.settings import settings

log = logging.getLogger(__name__)

_SCORE_BY_LEVEL = {"none": 0, "low": 20, "medium": 50, "high": 75, "critical": 95}
_STORE_THRESHOLD = "medium"  # only persist encrypted blob if severity >= this
_SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

VALID_TIERS = {"full", "vision_only", "text_only"}


def _ulid() -> str:
    return str(ULID())


def _apply_policy(session, profile_id, severity, categories, age_group="10_13"):
    """Resolve the child's privacy/threshold policy into an alert decision."""
    from app.services import profile_policy
    if severity == "none":
        return profile_policy.Decision(False, False, "no_risk")
    prof = session.get(ChildProfile, profile_id) if profile_id else None
    if prof is not None:
        pol = profile_policy.normalize(prof.alert_policy or {}, prof.age_group)
    else:
        # Unassigned device: age default (balanced for 10_13 — alert medium+, notify high+).
        pol = profile_policy.default_policy_for_age(age_group)
    return profile_policy.decide(pol, severity, categories)


def _should_store(severity: str) -> bool:
    return _SEVERITY_ORDER.get(severity, 0) >= _SEVERITY_ORDER[_STORE_THRESHOLD]


def _rules_result_from_matches(matches: list[risk_rules.RuleMatch]) -> dict[str, Any]:
    rules_severity = risk_rules.max_severity(matches)
    return {
        "risk_level": rules_severity,
        "score": _SCORE_BY_LEVEL.get(rules_severity, 0),
        "categories": risk_rules.aggregated_categories(matches),
        "summary": "",
        "evidence": [m.matched_text for m in matches],
        "recommended_action": "emergency_review" if rules_severity == "critical" else "alert_parent",
        "rules_triggered": [m.rule_id for m in matches],
        "confidence": max(m.confidence for m in matches),
        "rules_version": risk_rules.RULES_VERSION,
    }


def _apply_rules_floor(current: dict[str, Any], rules_result: dict[str, Any]) -> dict[str, Any]:
    """Merge deterministic rules into a text result as a minimum severity floor."""
    if not rules_result:
        return current
    if not current:
        return rules_result

    current_level = current.get("risk_level", "none")
    rules_level = rules_result.get("risk_level", "none")
    rules_are_higher = _SEVERITY_ORDER.get(rules_level, 0) > _SEVERITY_ORDER.get(current_level, 0)
    base = dict(rules_result if rules_are_higher else current)
    other = current if rules_are_higher else rules_result

    base["categories"] = sorted(set((base.get("categories") or []) + (other.get("categories") or [])))
    base["evidence"] = list(dict.fromkeys((base.get("evidence") or []) + (other.get("evidence") or [])))[:10]
    base["rules_triggered"] = sorted(set((current.get("rules_triggered") or []) + (rules_result.get("rules_triggered") or [])))
    base["rules_version"] = rules_result.get("rules_version") or current.get("rules_version")
    base["confidence"] = max(float(current.get("confidence", 0.0) or 0.0), float(rules_result.get("confidence", 0.0) or 0.0))
    if rules_are_higher:
        base["summary"] = current.get("summary", "") or rules_result.get("summary", "")
    return base


def _blob_path(blob_id: str) -> Path:
    # Shard into subdirs by hash prefix to avoid one big directory
    return settings.evidence_dir / blob_id[:2] / f"{blob_id}.enc"


async def _vision_available() -> tuple[bool, list[str]]:
    """Check if a vision-capable model is installed on Ollama."""
    try:
        client = OllamaClient(base_url=settings.vision_ollama_url_resolved)
        s = await client.status()
        if not s.available:
            return False, []
        vision_keywords = ("vl", "vision", "llava", "moondream", "minicpm-v", "qwen2-vl", "qwen2.5-vl")
        vision_models = [m for m in s.models if any(k in m.lower() for k in vision_keywords)]
        return len(vision_models) > 0, vision_models
    except Exception:
        return False, []


def _tesseract_extract(image_bytes: bytes) -> str:
    """Server-side OCR. No-op if pytesseract or the Tesseract binary is unavailable."""
    if not settings.tesseract_enabled:
        return ""
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageOps  # type: ignore

        img = Image.open(io.BytesIO(image_bytes))

        def _ocr(region: Image.Image) -> str:
            # Terminal and browser text can be only a few pixels tall in full-screen
            # captures. Upscaling a contrast-normalized grayscale copy materially
            # improves exact phrase OCR while keeping the longest edge bounded.
            gray = ImageOps.autocontrast(ImageOps.grayscale(region))
            scale = min(3.0, 4800 / max(gray.size))
            if scale > 1:
                gray = gray.resize(
                    (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            return pytesseract.image_to_string(gray, config="--psm 6").strip()

        readings = [_ocr(img)]
        if img.width >= img.height * 1.4:
            # A full desktop commonly contains side-by-side windows. Overlapping
            # pane passes prevent one column from corrupting the other's layout.
            pane_width = int(img.width * 0.6)
            readings.extend(
                (
                    _ocr(img.crop((0, 0, pane_width, img.height))),
                    _ocr(img.crop((img.width - pane_width, 0, img.width, img.height))),
                )
            )
        return _merge_ocr_text(*readings)
    except Exception as e:
        log.debug("tesseract fallback unavailable: %s", e)
        return ""


def _merge_ocr_text(*values: str) -> str:
    """Keep distinct OCR readings so deterministic rules can inspect both."""
    merged: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text not in merged:
            merged.append(text)
    return "\n".join(merged)


async def ingest_screenshot(
    session: Session,
    *,
    image_bytes: bytes,
    device_id: str,
    app_name: str | None = None,
    window_title: str | None = None,
    url: str | None = None,
    profile_id: str | None = None,
    age_group: str = "10_13",
    capture_scope: str = "monitored_app",
    policy_id: str | None = None,
    policy_version: str | None = None,
    collector_version: str | None = None,
    mime_type: str = "image/jpeg",
    timestamp: datetime | None = None,
    source_ip: str | None = None,
) -> dict[str, Any]:
    """Run the tiered pipeline. Returns result dict (also writes DB rows)."""
    timestamp = timestamp or datetime.now(UTC)
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    event_id = _ulid()
    tier = settings.classifier_tier if settings.classifier_tier in VALID_TIERS else "vision_only"

    # Register this frame as in-flight so the dashboard health widget can see it.
    pipeline_metrics.start(
        event_id=event_id,
        tier=tier,
        app_name=app_name,
        window_title=window_title,
        device_id=device_id,
    )
    severity_for_metrics = "none"
    try:
        result = await _ingest_inner(
            session,
            event_id=event_id,
            sha256=sha256,
            tier=tier,
            image_bytes=image_bytes,
            device_id=device_id,
            app_name=app_name,
            window_title=window_title,
            url=url,
            profile_id=profile_id,
            age_group=age_group,
            capture_scope=capture_scope,
            policy_id=policy_id,
            policy_version=policy_version,
            collector_version=collector_version,
            mime_type=mime_type,
            timestamp=timestamp,
            source_ip=source_ip,
        )
        severity_for_metrics = result.get("risk_level", "none")
        return result
    finally:
        pipeline_metrics.finish(event_id, severity=severity_for_metrics)


async def _ingest_inner(
    session: Session,
    *,
    event_id: str,
    sha256: str,
    tier: str,
    image_bytes: bytes,
    device_id: str,
    app_name: str | None,
    window_title: str | None,
    url: str | None,
    profile_id: str | None,
    age_group: str,
    capture_scope: str,
    policy_id: str | None,
    policy_version: str | None,
    collector_version: str | None,
    mime_type: str,
    timestamp: datetime,
    source_ip: str | None,
) -> dict[str, Any]:
    vision_result: dict[str, Any] = {}
    text_result: dict[str, Any] = {}
    extracted_text = ""
    tesseract_used = False

    # Resolve the child profile the same way text-event ingest does. The
    # backend assignment is authoritative; device payload profile/age fields are
    # legacy hints only and may not select another child's policy.
    device = session.get(Device, device_id)
    resolved = resolve_profile(
        session,
        device=device,
        payload_profile_id=profile_id,
        payload_age_group=age_group,
    )
    profile_id = resolved.profile_id
    age_group = resolved.age_group
    custom_phrases = resolved.custom_phrases

    if tier == "text_only":
        # CPU path: Tesseract OCR + rules + small text LLM (e.g. llama3.2:1b)
        log.info("screenshot %s → tier=text_only (Tesseract + text LLM)", event_id)
        pipeline_metrics.set_stage(event_id, "tesseract")
        extracted_text = _tesseract_extract(image_bytes)
        tesseract_used = bool(extracted_text)
        if extracted_text:
            pipeline_metrics.set_stage(event_id, "text_llm")
            text_result = await classifier.classify_text(
                redacted_text=extracted_text,
                app_name=app_name, source_type="image",
                age_group=age_group, timestamp=timestamp.isoformat(), url=url,
                custom_phrases=custom_phrases,
            )

    elif tier == "vision_only":
        # Run deterministic OCR alongside vision. Exact watch phrases must not
        # disappear when a reachable vision model returns empty or malformed OCR.
        log.info("screenshot %s → tier=vision_only (vision LLM + Tesseract + rules)", event_id)
        available, vision_models = await _vision_available()
        if available:
            chosen = settings.vision_model if settings.vision_model in vision_models else vision_models[0]
            pipeline_metrics.set_stage(event_id, "vision+tesseract")
            vision_task = asyncio.create_task(
                image_safety.classify_image(
                    image_bytes=image_bytes,
                    app_name=app_name, source_type="image",
                    age_group=age_group, timestamp=timestamp.isoformat(),
                    related_ocr_text="", watch_phrases=custom_phrases, model=chosen,
                )
            )
            tess_task = asyncio.create_task(asyncio.to_thread(_tesseract_extract, image_bytes))
            vision_result, tess_text = await asyncio.gather(vision_task, tess_task)
            tesseract_used = bool(tess_text)
            extracted_text = _merge_ocr_text(
                vision_result.get("visible_text") or "",
                tess_text,
            )
        else:
            log.warning("vision_only tier but no vision model; falling back to Tesseract")
            pipeline_metrics.set_stage(event_id, "tesseract")
            extracted_text = _tesseract_extract(image_bytes)
            tesseract_used = bool(extracted_text)
        # Rules engine on text (free, deterministic, no LLM cost).
        # Includes any parent-configured custom watch phrases for this profile.
        if extracted_text:
            pipeline_metrics.set_stage(event_id, "rules")
            matches = risk_rules.evaluate(extracted_text, custom_phrases=custom_phrases)
            if matches:
                text_result = _rules_result_from_matches(matches)

    else:  # tier == "full"
        # GPU path: vision LLM + text LLM run in PARALLEL. Vision does OCR +
        # image classification; text LLM does nuanced classification on
        # extracted text. Both models stay hot via keep_alive=24h.
        log.info("screenshot %s → tier=full (vision + text LLM, parallel)", event_id)
        pipeline_metrics.set_stage(event_id, "vision+text_parallel")
        available, vision_models = await _vision_available()
        chosen_vision = (
            settings.vision_model if (available and settings.vision_model in vision_models)
            else (vision_models[0] if available else None)
        )

        async def _vision_call() -> dict[str, Any]:
            if not chosen_vision:
                return {}
            return await image_safety.classify_image(
                image_bytes=image_bytes,
                app_name=app_name, source_type="image",
                age_group=age_group, timestamp=timestamp.isoformat(),
                related_ocr_text="", watch_phrases=custom_phrases, model=chosen_vision,
            )

        async def _text_path() -> tuple[str, dict[str, Any]]:
            # Tesseract first (~1s), then text LLM. Runs concurrently with vision call.
            t = _tesseract_extract(image_bytes)
            if not t:
                return "", {}
            tr = await classifier.classify_text(
                redacted_text=t,
                app_name=app_name, source_type="image",
                age_group=age_group, timestamp=timestamp.isoformat(), url=url,
                custom_phrases=custom_phrases,
            )
            return t, tr

        vision_task = asyncio.create_task(_vision_call())
        text_task = asyncio.create_task(_text_path())
        vision_result = await vision_task
        tess_text, text_result = await text_task
        tesseract_used = bool(tess_text)
        extracted_text = _merge_ocr_text(
            vision_result.get("visible_text") or "",
            tess_text,
        )

    # Apply deterministic rules to the final OCR text for every tier. In the
    # full tier, Tesseract can miss text that the vision model reads correctly;
    # this keeps known critical phrases from being softened by the LLM result.
    if extracted_text:
        pipeline_metrics.set_stage(event_id, "rules")
        matches = risk_rules.evaluate(extracted_text, custom_phrases=custom_phrases)
        if matches:
            text_result = _apply_rules_floor(text_result, _rules_result_from_matches(matches))

    # ----- Merge -----
    merged = multimodal_risk.merge(
        text_result=text_result or None,
        vision_result=vision_result or None,
    )
    severity = merged["risk_level"]

    # ----- Step 4: Persist event + (optional) blob -----
    blob_id: str | None = None
    if _should_store(severity):
        blob_id = _ulid()
        blob_path = _blob_path(blob_id)
        encryption.encrypt_blob_to_disk(image_bytes, blob_path, aad=blob_id.encode("ascii"))
        session.add(
            EvidenceBlob(
                blob_id=blob_id,
                kind="screenshot",
                mime_type=mime_type if mime_type in {"image/jpeg", "image/png"} else "image/jpeg",
                encrypted_path=str(blob_path),
                size_bytes=len(image_bytes),
                sha256_plain=sha256,
                key_version=encryption.current_key_version(),
                event_id=event_id,
            )
        )

    redacted_text_enc = encryption.encrypt_text(extracted_text) if extracted_text else None

    event = Event(
        event_id=event_id,
        device_id=device_id,
        profile_id=profile_id,
        source_type="image",
        app_name=app_name,
        window_title=window_title,
        url=url,
        timestamp=timestamp,
        redacted_text_enc=redacted_text_enc,
        evidence_type="image_ref",
        screenshot_blob_id=blob_id,
        event_metadata={
            "sha256": sha256,
            "image_bytes": len(image_bytes),
            "mime_type": mime_type if mime_type in {"image/jpeg", "image/png"} else "image/jpeg",
            "tier": tier,
            "capture_scope": capture_scope,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "collector_version": collector_version,
            "storage": "encrypted" if blob_id else "discarded_after_classification",
            "vision_model": vision_result.get("model"),
            "text_model": text_result.get("model"),
            "vision_used": bool(vision_result),
            "tesseract_used": tesseract_used,
            "extracted_text_chars": len(extracted_text),
        },
        received_at=datetime.now(UTC),
        key_version=encryption.current_key_version(),
    )
    session.add(event)

    # Update device heartbeat
    if device is not None:
        device.last_seen = datetime.now(UTC)
        device.status = "online"
    session.flush()

    # ----- Step 5: RiskResult -----
    risk_id = _ulid()
    rr = RiskResult(
        risk_id=risk_id,
        event_id=event_id,
        risk_level=severity,
        score=int(merged.get("score", 0)),
        categories=merged.get("categories", []),
        summary=merged.get("summary", "") or vision_result.get("summary", "") or text_result.get("summary", ""),
        evidence=merged.get("evidence", []),
        recommended_action=merged.get("recommended_action", "none"),
        model=(vision_result.get("model") or text_result.get("model")),
        rules_triggered=text_result.get("rules_triggered", []),
        confidence=float(merged.get("confidence", 0.0)),
        false_positive_notes="",
        prompt_version=vision_result.get("prompt_version") or text_result.get("prompt_version"),
        rules_version=text_result.get("rules_version"),
        # Reduced-protection marker: no model judged this frame (vision missing
        # or failed AND the text LLM never produced a result). Rules still ran.
        classifier_status=(
            "ok"
            if (vision_result.get("model") or text_result.get("model") or text_result.get("status") == "ok")
            else "unclassified_model_unavailable"
        ),
    )
    session.add(rr)
    session.flush()

    # ----- Step 6: Alert per the child's privacy/threshold policy -----
    alert_id: str | None = None
    cats = merged.get("categories", [])
    decision = _apply_policy(session, profile_id, severity, cats, age_group=age_group)
    if decision.create_alert:
        from app.services.alert_dedup import upsert_alert
        alert_id, _created = upsert_alert(
            session,
            risk_id=risk_id,
            device_id=device_id,
            profile_id=profile_id,
            severity=severity,
            categories=cats,
            source="screenshot",
            source_ip=source_ip,
            notify=decision.notify,
            risk_summary=merged.get("summary", ""),
        )

    return {
        "event_id": event_id,
        "risk_id": risk_id,
        "alert_id": alert_id,
        "risk_level": severity,
        "score": int(merged.get("score", 0)),
        "categories": merged.get("categories", []),
        "blob_stored": blob_id is not None,
        "vision_used": bool(vision_result),
        "extracted_text_chars": len(extracted_text),
    }
