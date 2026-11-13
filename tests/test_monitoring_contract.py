"""Keep exported contracts aligned with the screenshot-review product boundary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.python.schemas import Policy, RecommendedAction, RiskResult


def test_risk_contract_cannot_request_device_restrictions() -> None:
    schema = json.loads((ROOT / "shared/schemas/risk_result.json").read_text())
    actions = set(schema["properties"]["recommended_action"]["enum"])
    assert actions == {item.value for item in RecommendedAction}
    assert actions == {"none", "log", "alert_parent", "emergency_review"}
    for retired in ("pause_app", "block_app", "block_domain", "kill_app"):
        with pytest.raises(ValidationError):
            RiskResult(
                risk_id="synthetic-risk", event_id="synthetic-frame",
                risk_level="high", score=75, recommended_action=retired,
            )


def test_shared_policy_keeps_capture_controls_and_rejects_restrictions() -> None:
    schema = json.loads((ROOT / "shared/schemas/policy.json").read_text())
    assert schema["additionalProperties"] is False
    base = {"policy_id": "synthetic-policy", "profile_id": "synthetic-profile"}
    policy = Policy(**base, monitored_apps=["example.exe"], ocr_cadence_seconds=5)
    assert policy.monitored_apps == ["example.exe"]
    for retired in ("enforcement", "schedules", "screen_time_limits", "blocked_domains"):
        assert retired not in schema["properties"]
        with pytest.raises(ValidationError):
            Policy(**base, **{retired: {"enabled": True}})
