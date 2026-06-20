"""Tests for the deterministic rules engine."""
from __future__ import annotations

from app.services import risk_rules


def _ids(matches):
    return {m.rule_id for m in matches}


def test_off_platform_contact_snap():
    m = risk_rules.evaluate("hey add me on snap pls")
    assert "off_platform_contact" in _ids(m)


def test_off_platform_contact_discord():
    m = risk_rules.evaluate("dm me on discord later")
    assert "off_platform_contact" in _ids(m)


def test_secrecy_critical():
    m = risk_rules.evaluate("don't tell your parents about this")
    assert "grooming_secrecy_critical" in _ids(m)
    assert risk_rules.max_severity(m) == "critical"


def test_private_info_request():
    m = risk_rules.evaluate("what school do you go to btw?")
    assert "private_info_request" in _ids(m)


def test_robux_scam():
    m = risk_rules.evaluate("free robux click here")
    assert "scam_robux_giftcard" in _ids(m)


def test_phishing_shortener():
    m = risk_rules.evaluate("verify here https://bit.ly/abc123")
    assert "phishing_link_shorteners" in _ids(m)


def test_self_harm_imminent_critical():
    m = risk_rules.evaluate("i am going to kill myself tonight")
    assert "self_harm_imminent" in _ids(m)
    assert risk_rules.max_severity(m) == "critical"


def test_send_pic_critical():
    m = risk_rules.evaluate("send me a pic of you")
    assert "grooming_send_pic_minor_context" in _ids(m)
    assert risk_rules.max_severity(m) == "critical"


def test_bullying_kys():
    m = risk_rules.evaluate("kys you loser")
    assert "bullying_keywords" in _ids(m)


def test_safe_text_no_match():
    m = risk_rules.evaluate("we are playing minecraft after dinner")
    assert m == []


def test_aggregated_categories():
    m = risk_rules.evaluate("add me on snap and don't tell your parents")
    cats = risk_rules.aggregated_categories(m)
    assert "off_platform_contact" in cats
    assert "secrecy_request" in cats


def test_no_text_no_match():
    assert risk_rules.evaluate("") == []
