"""Per-child privacy/threshold policy resolver."""
from __future__ import annotations

from app.services import profile_policy as pp


def D(age):
    return pp.default_policy_for_age(age)


def test_protected_categories_always_alert_regardless_of_age():
    # Even the most privacy-forward (14_17) policy must alert on self-harm/grooming.
    pol = D("14_17")
    for cat in ("self_harm", "grooming", "threat", "custom_watch"):
        d = pp.decide(pol, "high", [cat])
        assert d.create_alert and d.notify, cat


def test_teen_profanity_is_allowed():
    # "At a certain age curse words don't matter as much."
    d = pp.decide(D("14_17"), "low", ["profanity"])
    assert not d.create_alert


def test_young_child_profanity_alerts():
    d = pp.decide(D("under_10"), "low", ["profanity"])
    assert d.create_alert


def test_teen_romantic_talk_private_unless_serious():
    pol = D("14_17")  # sexual_content -> alert only at critical
    # Ordinary romantic/sexual chat at high severity -> not alerted (private).
    assert not pp.decide(pol, "high", ["sexual_content"]).create_alert
    # Escalates to critical -> alerts.
    assert pp.decide(pol, "critical", ["sexual_content"]).create_alert


def test_monitor_creates_alert_without_notification():
    # 10_13 profanity is "monitor" -> recorded but no email.
    d = pp.decide(D("10_13"), "medium", ["profanity"])
    assert d.create_alert and not d.notify


def test_global_floor_suppresses_low_severity():
    # 14_17 min_severity is high; a medium scam shouldn't alert...
    pol = D("14_17")
    # scam is alert@high in the preset, so medium is below floor.
    assert not pp.decide(pol, "medium", ["scam"]).create_alert
    assert pp.decide(pol, "high", ["scam"]).create_alert


def test_category_floor_cannot_lower_global_floor():
    pol = {
        "min_severity": "critical",
        "categories": {
            "scam": {"mode": "alert", "min_severity": "low"},
            "drugs": {"mode": "monitor", "min_severity": "medium"},
        },
    }

    assert not pp.decide(pol, "high", ["scam"]).create_alert
    assert not pp.decide(pol, "high", ["drugs"]).create_alert
    assert pp.decide(pol, "critical", ["scam"]).create_alert


def test_capture_settings_by_level():
    tight = pp.capture_settings({"capture": {"level": "tight"}})
    leeway = pp.capture_settings({"capture": {"level": "leeway"}})
    assert tight["cadence_seconds"] < leeway["cadence_seconds"]
    assert tight["phash_threshold"] <= leeway["phash_threshold"]
    assert tight["max_capture_interval_seconds"] < leeway["max_capture_interval_seconds"]


def test_capture_settings_can_override_max_interval():
    cfg = pp.capture_settings({"capture": {"level": "balanced", "max_capture_interval_seconds": 45}})
    assert cfg["max_capture_interval_seconds"] == 45


def test_normalize_fills_age_defaults():
    pol = pp.normalize({"min_severity": "critical"}, "10_13")
    assert pol["min_severity"] == "critical"
    assert "categories" in pol and "capture" in pol
