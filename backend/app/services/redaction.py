"""Secrets redaction.

Strips likely passwords, API keys, card numbers, SSNs, 2FA codes, recovery
phrases, and PEM blocks from text before it is classified or stored.

The goal is best-effort. False positives are acceptable; false negatives are
worse. Defense-in-depth: the agent and the backend both run this.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Reserved for curated phrase hints; structural 12/24-word detection is primary.
_BIP39_HINT_WORDS: set[str] = set()


@dataclass
class RedactionResult:
    redacted_text: str
    summary: dict[str, int]


_PEM_RE = re.compile(
    r"-----BEGIN [A-Z ]+-----[\s\S]+?-----END [A-Z ]+-----", re.MULTILINE
)
_API_KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|xox[bopas]-[A-Za-z0-9-]{10,}|"
    r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35})\b"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.=]+\b")
_2FA_RE = re.compile(
    r"(?i)\b(?:code|verification|2fa|otp|pin)\s*(?:[:=]|is|->)?\s*(\d{4,8})\b"
)
_PASSWORD_RE = re.compile(
    r"(?i)\b(?:password|pwd|passwd)\s*[:=]\s*([^\s,;]+)"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_BIP39_LINE_RE = re.compile(
    r"\b((?:[a-z]{3,8}\s+){11,23}[a-z]{3,8})\b"
)


def _luhn_ok(num: str) -> bool:
    digits = [int(c) for c in num if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    s = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return s % 10 == 0


def redact(text: str) -> RedactionResult:
    """Redact obvious secrets. Returns redacted text and a count summary."""
    if not text:
        return RedactionResult(text or "", {})

    summary: dict[str, int] = {}

    def _count(tag: str) -> None:
        summary[tag] = summary.get(tag, 0) + 1

    def sub_with_count(pattern: re.Pattern[str], repl_tag: str, text: str) -> str:
        def _repl(_match: re.Match[str]) -> str:
            _count(repl_tag)
            return f"[REDACTED:{repl_tag}]"

        return pattern.sub(_repl, text)

    # PEM blocks first (they span multiple lines)
    text = sub_with_count(_PEM_RE, "privkey", text)

    # API keys
    text = sub_with_count(_API_KEY_RE, "apikey", text)

    # Bearer tokens
    text = sub_with_count(_BEARER_RE, "apikey", text)

    # 2FA / verification codes — only the digits, not the surrounding label
    def _sub_2fa(m: re.Match[str]) -> str:
        _count("2fa")
        return m.group(0).replace(m.group(1), "[REDACTED:2fa]")

    text = _2FA_RE.sub(_sub_2fa, text)

    # Passwords after marker
    def _sub_pwd(m: re.Match[str]) -> str:
        _count("pwd")
        return m.group(0).replace(m.group(1), "[REDACTED:pwd]")

    text = _PASSWORD_RE.sub(_sub_pwd, text)

    # SSN
    text = sub_with_count(_SSN_RE, "ssn", text)

    # Cards — Luhn-validate to reduce false positives
    def _sub_card(m: re.Match[str]) -> str:
        candidate = m.group(0)
        if _luhn_ok(candidate):
            _count("card")
            return "[REDACTED:card]"
        return candidate

    text = _CARD_CANDIDATE_RE.sub(_sub_card, text)

    # BIP39-like sequences
    def _sub_seed(m: re.Match[str]) -> str:
        seq = m.group(1).split()
        if len(seq) in (12, 15, 18, 21, 24) and all(3 <= len(w) <= 8 for w in seq):
            _count("seed")
            return "[REDACTED:seed]"
        return m.group(0)

    text = _BIP39_LINE_RE.sub(_sub_seed, text)

    return RedactionResult(text, summary)
