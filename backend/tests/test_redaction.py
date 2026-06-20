"""Tests for the redaction engine."""
from __future__ import annotations

from app.services.redaction import redact


def test_redacts_credit_card_luhn_valid():
    text = "my card is 4111 1111 1111 1111 please charge it"
    r = redact(text)
    assert "[REDACTED:card]" in r.redacted_text
    assert "4111" not in r.redacted_text
    assert r.summary.get("card") == 1


def test_ignores_random_16_digits_failing_luhn():
    text = "the room number is 1234 5678 9012 3456 thanks"
    r = redact(text)
    # Likely fails Luhn; should remain
    if "[REDACTED:card]" in r.redacted_text:
        assert False, "should not have flagged"


def test_redacts_ssn():
    r = redact("my SSN is 123-45-6789 ok?")
    assert "[REDACTED:ssn]" in r.redacted_text
    assert r.summary.get("ssn") == 1


def test_redacts_api_keys():
    text = "use this token sk-abcdef1234567890ABCDEF for the API"
    r = redact(text)
    assert "[REDACTED:apikey]" in r.redacted_text
    assert "sk-abcdef" not in r.redacted_text


def test_redacts_bearer_token():
    text = "Authorization: Bearer abcXYZ.123-456_xyz"
    r = redact(text)
    assert "[REDACTED:apikey]" in r.redacted_text


def test_redacts_2fa_code():
    text = "your verification code is 482910 dont share it"
    r = redact(text)
    assert "[REDACTED:2fa]" in r.redacted_text
    assert r.summary.get("2fa") == 1


def test_redacts_password_marker():
    text = "password: hunter2 should be private"
    r = redact(text)
    assert "[REDACTED:pwd]" in r.redacted_text


def test_redacts_pem_block():
    text = (
        "Here is my key:\n"
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...\n"
        "-----END PRIVATE KEY-----\n"
        "do not share"
    )
    r = redact(text)
    assert "[REDACTED:privkey]" in r.redacted_text
    assert "BEGIN" not in r.redacted_text


def test_keeps_safe_text():
    text = "hey want to play roblox after school"
    r = redact(text)
    assert r.redacted_text == text


def test_empty_text():
    r = redact("")
    assert r.redacted_text == ""
    assert r.summary == {}
