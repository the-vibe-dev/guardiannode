"""Text classification pipeline: rules + Ollama LLM merge.

Returns a `RiskResult` Pydantic model.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.services import risk_rules
from app.services.ollama_client import OllamaClient, OllamaError
from app.settings import settings

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "text_classifier.txt"
_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _prompt_version() -> str:
    return hashlib.sha256(_prompt_template().encode("utf-8")).hexdigest()[:8]


_SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_SEVERITY_NAMES = ["none", "low", "medium", "high", "critical"]


def _max_severity(a: str, b: str) -> str:
    return _SEVERITY_NAMES[max(_SEVERITY_ORDER.get(a, 0), _SEVERITY_ORDER.get(b, 0))]


def _extract_json(s: str) -> dict[str, Any] | None:
    if not s:
        return None
    s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = _JSON_RE.search(s)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _normalize_llm(parsed: dict[str, Any]) -> dict[str, Any]:
    risk_level = parsed.get("risk_level", "none")
    if risk_level not in _SEVERITY_ORDER:
        risk_level = "none"
    score = parsed.get("score", 0)
    try:
        score = int(score)
    except Exception:
        score = 0
    score = max(0, min(100, score))
    categories = parsed.get("categories") or []
    if not isinstance(categories, list):
        categories = []
    summary = str(parsed.get("summary", ""))[:2048]
    evidence = parsed.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    evidence = [str(e)[:1024] for e in evidence[:10]]
    action = parsed.get("recommended_action", "none")
    if action not in {"none", "log", "alert_parent", "pause_app", "block_app", "emergency_review"}:
        action = "none"
    confidence = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    notes = str(parsed.get("false_positive_notes", ""))[:2048]
    return {
        "risk_level": risk_level,
        "score": score,
        "categories": categories,
        "summary": summary,
        "evidence": evidence,
        "recommended_action": action,
        "confidence": confidence,
        "false_positive_notes": notes,
    }


async def classify_text(
    *,
    redacted_text: str,
    app_name: str | None = None,
    source_type: str = "ocr",
    age_group: str = "10_13",
    timestamp: str = "",
    url: str | None = None,
    model: str | None = None,
    use_llm: bool = True,
    custom_phrases: list[str] | None = None,
) -> dict[str, Any]:
    """Run rules + LLM, return a merged result dict ready for RiskResult."""

    # 1) Rules (built-ins + any parent-configured custom watch phrases)
    matches = risk_rules.evaluate(redacted_text or "", custom_phrases=custom_phrases)
    rules_severity = risk_rules.max_severity(matches)
    rules_categories = risk_rules.aggregated_categories(matches)
    rules_score = {
        "none": 0,
        "low": 20,
        "medium": 50,
        "high": 75,
        "critical": 95,
    }[rules_severity]

    # 2) LLM (best effort)
    llm: dict[str, Any] = {
        "risk_level": "none",
        "score": 0,
        "categories": [],
        "summary": "",
        "evidence": [],
        "recommended_action": "none",
        "confidence": 0.0,
        "false_positive_notes": "",
    }
    llm_used = False
    llm_error: str | None = None

    chosen_model = model or settings.text_model

    if use_llm and (redacted_text or "").strip():
        client = OllamaClient(
            base_url=settings.text_ollama_url_resolved,
            timeout=settings.classifier_timeout_seconds,
        )
        prompt = _prompt_template().format(
            app_name=app_name or "unknown",
            source_type=source_type,
            age_group=age_group,
            timestamp=timestamp,
            url=url or "none",
            rules_triggered=", ".join(m.rule_id for m in matches) or "none",
            text=redacted_text,
        )
        for attempt in range(2):
            try:
                response = await client.generate(
                    model=chosen_model,
                    prompt=prompt,
                    options={"temperature": 0.2, "num_ctx": 4096},
                    format_json=True,
                )
                parsed = _extract_json(response)
                if parsed is not None:
                    llm = _normalize_llm(parsed)
                    llm_used = True
                    break
                # one retry with correction prompt
                if attempt == 0:
                    prompt = (
                        prompt
                        + "\n\nYour previous response was not valid JSON. Return ONLY the JSON object now."
                    )
                    continue
            except OllamaError as e:
                llm_error = str(e)
                break
            except Exception as e:
                llm_error = str(e)
                break

    # 3) Merge
    # Rules has higher weight at critical; LLM has more weight at medium/high.
    if rules_severity == "critical":
        final_score = max(rules_score, llm["score"])
        final_level = _max_severity("critical", llm["risk_level"])
    else:
        # Weighted average if both present, else use whichever is non-zero.
        if llm_used:
            final_score = int(round(0.5 * rules_score + 0.5 * llm["score"]))
        else:
            final_score = rules_score
        final_level = _max_severity(rules_severity, llm["risk_level"])

    final_categories = sorted(set(rules_categories) | set(llm["categories"]))
    final_evidence = []
    seen = set()
    for ev in llm["evidence"]:
        if ev and ev not in seen:
            final_evidence.append(ev)
            seen.add(ev)
    for m_ in matches:
        if m_.matched_text and m_.matched_text not in seen:
            final_evidence.append(m_.matched_text)
            seen.add(m_.matched_text)

    # recommended action: prefer LLM, but override critical → at least alert_parent
    action = llm["recommended_action"]
    if final_level == "critical" and action in ("none", "log"):
        action = "alert_parent"
    elif final_level == "high" and action == "none":
        action = "alert_parent"
    elif final_level == "medium" and action == "none":
        action = "log"

    # Prefer the LLM's natural-language summary. If no LLM ran, build a clean
    # rules-only summary from category names (not the noisy concat that was
    # showing up in the dashboard).
    if llm["summary"]:
        summary = llm["summary"]
    elif rules_categories:
        cat_human = {
            "off_platform_contact": "off-platform contact request",
            "secrecy_request": "secrecy / coercion language",
            "private_info_request": "private-info request (address/school/phone)",
            "scam": "scam (Robux / gift-card / money)",
            "phishing": "suspicious link",
            "grooming": "grooming pattern",
            "sexual_content": "sexual content request",
            "self_harm": "self-harm language",
            "bullying": "bullying / harassment",
            "threat": "credible threat",
        }
        parts = [cat_human.get(c, c.replace("_", " ")) for c in rules_categories]
        summary = "Detected: " + ", ".join(parts) + "."
    else:
        summary = ""

    return {
        "risk_level": final_level,
        "score": max(0, min(100, final_score)),
        "categories": final_categories,
        "summary": summary,
        "evidence": final_evidence[:10],
        "recommended_action": action,
        "model": chosen_model if llm_used else None,
        "rules_triggered": [m.rule_id for m in matches],
        "confidence": max(
            llm["confidence"] if llm_used else 0.0,
            max((m.confidence for m in matches), default=0.0),
        ),
        "false_positive_notes": llm["false_positive_notes"],
        "prompt_version": _prompt_version(),
        "rules_version": risk_rules.RULES_VERSION,
        "_llm_used": llm_used,
        "_llm_error": llm_error,
    }
