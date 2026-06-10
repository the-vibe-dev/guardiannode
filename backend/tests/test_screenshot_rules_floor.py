from __future__ import annotations

from app.services import risk_rules
from app.services.screenshot_ingest import _apply_rules_floor, _rules_result_from_matches


def test_rules_floor_promotes_vision_ocr_text_to_critical():
    model_result = {
        "risk_level": "high",
        "score": 85,
        "categories": ["self_harm", "sexual_content"],
        "summary": "Model saw risky text.",
        "evidence": ["model evidence"],
        "recommended_action": "alert_parent",
        "confidence": 0.8,
    }
    matches = risk_rules.evaluate(
        "i am going to kill myself tonight. don't tell your parents. send me a pic"
    )

    merged = _apply_rules_floor(model_result, _rules_result_from_matches(matches))

    assert merged["risk_level"] == "critical"
    assert merged["score"] == 95
    assert merged["recommended_action"] == "emergency_review"
    assert "self_harm_imminent" in merged["rules_triggered"]
    assert "grooming_secrecy_critical" in merged["rules_triggered"]
