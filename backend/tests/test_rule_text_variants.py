"""Regression inputs for common English contractions and Unicode typography."""
from __future__ import annotations

import pytest

from app.services import risk_rules


@pytest.mark.parametrize("text", [
    "I'm going to hurt myself",
    "I’m going to kill myself",
    "I’m going to end my life",
    "I am going to take my life",
    "Ｉ ｗａｎｔ ｔｏ ｈｕｒｔ ｍｙｓｅｌｆ",
    "I want to hurt my\u200bself",
])
def test_imminent_self_harm_variants_keep_critical_floor(text):
    matches = risk_rules.evaluate(text)
    assert risk_rules.max_severity(matches) == "critical"
    assert "self_harm" in risk_rules.aggregated_categories(matches)


@pytest.mark.parametrize("text", ["I can't stand my life", "I can’t stand my life"])
def test_distress_contractions_match(text):
    assert risk_rules.max_severity(risk_rules.evaluate(text)) == "high"


def test_curly_apostrophe_threat_and_secrecy():
    assert risk_rules.max_severity(risk_rules.evaluate("I’ll kill you")) == "critical"
    assert risk_rules.max_severity(risk_rules.evaluate("Don’t tell your parents")) == "critical"


@pytest.mark.parametrize("text", [
    "I'm going to play Minecraft after dinner",
    "I’m not going to hurt myself; I am asking for help",
    "I can't stand this puzzle",
    "Let’s send a picture of the worksheet",
])
def test_normalization_does_not_create_signals_in_benign_variants(text):
    assert risk_rules.evaluate(text) == []


def test_custom_watch_phrase_uses_same_typographic_normalization():
    matches = risk_rules.evaluate("St. Mary’s School", custom_phrases=["St. Mary's School"])
    assert any(match.category == "custom_watch" for match in matches)
