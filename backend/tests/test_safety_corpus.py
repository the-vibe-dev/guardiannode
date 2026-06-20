"""Synthetic safety benchmark corpus (tests/fixtures/safety_cases/).

Runs every text-input case through the deterministic pipeline (rules +
normalization + profile policy) with the LLM disabled, so CI needs no model.
Cases marked ``requires: vision_tier`` document expected vision behavior and
are skipped here.

All fixture content is synthetic. No real child data, ever.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import profile_policy, risk_rules
from app.services.taxonomy import ALLOWED_CATEGORIES, SEVERITY_ORDER

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "safety_cases"

_CASES = sorted(
    p for p in FIXTURES.rglob("*.json")
    if json.loads(p.read_text("utf-8")).get("requires") != "vision_tier"
)


def _ids(paths):
    return [str(p.relative_to(FIXTURES)) for p in paths]


@pytest.mark.parametrize("case_path", _CASES, ids=_ids(_CASES))
@pytest.mark.asyncio
async def test_safety_case(case_path: Path):
    case = json.loads(case_path.read_text("utf-8"))
    expected = case["expected"]
    age_group = case.get("age_group", "10_13")
    phrases = case.get("custom_watch_phrases") or []

    from app.services import classifier

    result = await classifier.classify_text(
        redacted_text=case["text"],
        age_group=age_group,
        custom_phrases=phrases,
        use_llm=False,  # deterministic CI: rules + normalization only
    )

    severity = result["risk_level"]
    cats = result["categories"]

    # Stored categories are always canonical.
    assert all(c in ALLOWED_CATEGORIES for c in cats), f"non-canonical categories: {cats}"

    if "min_severity" in expected:
        assert SEVERITY_ORDER[severity] >= SEVERITY_ORDER[expected["min_severity"]], (
            f"{case['name']}: severity {severity} < expected {expected['min_severity']} "
            f"(categories={cats}, rules={result['rules_triggered']})"
        )
    if "max_severity" in expected:
        assert SEVERITY_ORDER[severity] <= SEVERITY_ORDER[expected["max_severity"]], (
            f"{case['name']}: severity {severity} > allowed {expected['max_severity']} "
            f"(categories={cats}, rules={result['rules_triggered']})"
        )
    if "categories_any" in expected:
        assert set(cats) & set(expected["categories_any"]), (
            f"{case['name']}: none of {expected['categories_any']} in {cats}"
        )

    # Policy decision: would this alert/notify the parent?
    policy = profile_policy.default_policy_for_age(age_group)
    if severity == "none":
        decision = profile_policy.Decision(False, False, "no_risk")
    else:
        decision = profile_policy.decide(policy, severity, cats)

    if "alert" in expected:
        assert decision.create_alert is expected["alert"], (
            f"{case['name']}: alert={decision.create_alert} expected {expected['alert']} "
            f"(severity={severity}, categories={cats}, reason={decision.reason})"
        )
    if expected.get("notify"):
        assert decision.notify is True, f"{case['name']}: expected parent notification"
    if "reason_contains" in expected:
        assert expected["reason_contains"] in decision.reason


def test_corpus_has_cases():
    assert len(_CASES) >= 12, "safety corpus unexpectedly small — fixtures missing?"


def test_corpus_is_synthetic_only():
    # Guard: fixtures must never carry real-looking PII markers.
    for p in FIXTURES.rglob("*.json"):
        body = p.read_text("utf-8").lower()
        assert "real_child" not in body
