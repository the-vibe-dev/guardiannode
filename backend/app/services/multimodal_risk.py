"""Merge text + vision + rules scores into a final risk assessment."""
from __future__ import annotations

from typing import Any

_LEVELS = ["none", "low", "medium", "high", "critical"]
_ORDER = {lvl: i for i, lvl in enumerate(_LEVELS)}


def merge(
    *,
    text_result: dict[str, Any] | None,
    vision_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combine text and vision classifier outputs.

    Strategy:
    - final_level = max severity across both
    - final_score = max(text_score, vision_score) when same severity tier,
                    else use the higher-tier's score
    - categories merged
    - evidence: text evidence first, then vision evidence (labeled)
    - confidence: weighted average if both, else from whichever exists
    """
    if not text_result and not vision_result:
        return {
            "risk_level": "none",
            "score": 0,
            "categories": [],
            "summary": "",
            "evidence": [],
            "recommended_action": "none",
            "confidence": 0.0,
        }

    t = text_result or {}
    v = vision_result or {}

    t_level = t.get("risk_level", "none")
    v_level = v.get("risk_level", "none")
    final_level = max(t_level, v_level, key=lambda lvl: _ORDER.get(lvl, 0))

    t_score = int(t.get("score", 0) or 0)
    v_score = int(v.get("score", 0) or 0)
    if _ORDER.get(t_level, 0) > _ORDER.get(v_level, 0):
        final_score = t_score
    elif _ORDER.get(v_level, 0) > _ORDER.get(t_level, 0):
        final_score = v_score
    else:
        final_score = max(t_score, v_score)

    categories = sorted(set((t.get("categories") or []) + (v.get("categories") or [])))

    # Build a deduped, ranked evidence list.
    raw = []
    for e in t.get("evidence") or []:
        if e:
            raw.append((str(e), "text"))
    for e in v.get("visual_evidence") or []:
        if e:
            raw.append((f"[image] {e}", "vision"))

    # Drop UI-chrome noise — strings that look like generic browser/OS elements.
    NOISE_PATTERNS = (
        "search google", "type a url", "[image] browser tab", "[image] google search bar",
        "[image] address bar", "[image] taskbar", "[image] menu bar", "[image] window controls",
        "add shortcut", "customize chrome", "web store", "[image] start menu",
    )
    def _is_noise(s: str) -> bool:
        low = s.lower()
        return any(p in low for p in NOISE_PATTERNS)

    # Dedupe by case-insensitive substring containment (keep the LONGEST form).
    cleaned: list[str] = []
    for s, _ in raw:
        if _is_noise(s):
            continue
        s_low = s.lower().strip()
        if not s_low:
            continue
        replace_idx = -1
        skip = False
        for i, existing in enumerate(cleaned):
            ex_low = existing.lower().strip()
            if s_low == ex_low:
                skip = True
                break
            if s_low in ex_low:
                # Existing is a superset, skip this one
                skip = True
                break
            if ex_low in s_low:
                # New is a superset, replace existing
                replace_idx = i
                break
        if skip:
            continue
        if replace_idx >= 0:
            cleaned[replace_idx] = s
        else:
            cleaned.append(s)
    evidence = cleaned[:5]

    # Prefer the vision summary if available (it sees the whole screen incl. images);
    # fall back to text summary. Avoid concatenating duplicates.
    v_sum = (v.get("summary") or "").strip()
    t_sum = (t.get("summary") or "").strip()
    if v_sum and t_sum and t_sum.lower() not in v_sum.lower() and v_sum.lower() not in t_sum.lower():
        summary = f"{v_sum} {t_sum}"[:2048]
    else:
        summary = (v_sum or t_sum)[:2048]

    t_conf = float(t.get("confidence", 0.0) or 0.0)
    v_conf = float(v.get("confidence", 0.0) or 0.0)
    if t and v:
        confidence = (t_conf + v_conf) / 2.0
    else:
        confidence = t_conf or v_conf

    # Pick action: prefer the stricter of the two
    action_priority = [
        "none",
        "log",
        "alert_parent",
        "pause_app",
        "block_app",
        "emergency_review",
    ]
    t_action = t.get("recommended_action", "none")
    v_action = v.get("recommended_action", "none")
    action = max(
        (t_action, v_action),
        key=lambda a: action_priority.index(a) if a in action_priority else 0,
    )

    if final_level == "critical" and action in ("none", "log"):
        action = "alert_parent"

    return {
        "risk_level": final_level,
        "score": final_score,
        "categories": categories,
        "summary": summary,
        "evidence": evidence[:10],
        "recommended_action": action,
        "confidence": round(confidence, 3),
    }
