"""Parent password + recovery code utilities."""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# A BIP39-style word list for the recovery code.
# This is NOT the official BIP39 list (which is 2048 words and licensed under
# specific terms). It is a project-specific list of ~1,350 short, easy-to-spell
# English words shipped as a resource file; see app/data/wordlist.txt.
# The recovery code is 12 words drawn from it: ~124 bits of entropy
# (12 × log2(1345) ≈ 124.7).

import os
from functools import lru_cache
from pathlib import Path

_PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


@lru_cache(maxsize=1)
def _load_wordlist() -> list[str]:
    p = Path(__file__).resolve().parent.parent / "data" / "wordlist.txt"
    if not p.exists():
        # Fallback: tiny built-in list (only used if the data file is missing —
        # the real install ships the full 2048-word list).
        return _BUILTIN_WORDS
    return [w.strip() for w in p.read_text("utf-8").splitlines() if w.strip()]


# Tiny fallback wordlist (256 short common words) — strictly a last-resort.
_BUILTIN_WORDS = [
    "able", "acid", "aged", "also", "area", "army", "away", "baby", "back", "ball",
    "band", "bank", "base", "bath", "bear", "beat", "been", "beer", "bell", "belt",
    "best", "bill", "bird", "blow", "blue", "boat", "body", "bomb", "bond", "bone",
    "book", "boom", "born", "boss", "both", "bowl", "bulk", "burn", "bush", "busy",
    "call", "calm", "came", "camp", "card", "care", "case", "cash", "cast", "cell",
    "chat", "chip", "city", "club", "coal", "coat", "code", "cold", "come", "cook",
    "cool", "cope", "copy", "core", "cost", "crew", "crop", "dark", "data", "date",
    "dawn", "days", "dead", "deal", "dean", "dear", "debt", "deep", "deny", "desk",
    "dial", "dice", "diet", "disc", "disk", "does", "done", "door", "dose", "down",
    "draw", "drew", "drop", "drug", "dual", "duke", "dust", "duty", "each", "earn",
    "ease", "east", "easy", "edge", "else", "even", "ever", "evil", "exit", "face",
    "fact", "fail", "fair", "fall", "farm", "fast", "fate", "fear", "feed", "feel",
    "fell", "felt", "file", "fill", "film", "find", "fine", "fire", "firm", "fish",
    "five", "flat", "flow", "food", "foot", "ford", "form", "fort", "four", "free",
    "from", "fuel", "full", "fund", "gain", "game", "gate", "gave", "gear", "gene",
    "gift", "girl", "give", "glad", "goal", "goes", "gold", "golf", "gone", "good",
    "gray", "grew", "grey", "grow", "gulf", "hair", "half", "hall", "hand", "hang",
    "hard", "harm", "hate", "have", "head", "hear", "heat", "held", "hell", "help",
    "here", "hero", "high", "hill", "hint", "hire", "hold", "hole", "holy", "home",
    "hope", "host", "hour", "huge", "hung", "hunt", "hurt", "idea", "inch", "into",
    "iron", "item", "jack", "jane", "jean", "jess", "join", "jump", "jury", "just",
    "keen", "keep", "kept", "kick", "kill", "kind", "king", "knee", "knew", "know",
    "lack", "lady", "laid", "lake", "land", "lane", "last", "late", "lead", "left",
    "less", "life", "lift", "like", "line", "link", "list", "live", "load", "loan",
    "lock", "logo", "long", "look", "lord", "lose", "loss", "lost", "love", "luck",
    "made", "mail", "main", "make",
]
_BUILTIN_WORDS = _BUILTIN_WORDS[:256]


@dataclass
class RecoveryCode:
    words: list[str]

    def as_string(self) -> str:
        return " ".join(self.words)


def hash_password(password: str) -> str:
    return _PH.hash(password)


def verify_password(password: str, hash_: str) -> bool:
    try:
        return _PH.verify(hash_, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_recovery_code(num_words: int = 12) -> RecoveryCode:
    words = _load_wordlist()
    if not words:
        raise RuntimeError("wordlist not available")
    chosen = [secrets.choice(words) for _ in range(num_words)]
    return RecoveryCode(chosen)


def hash_recovery_code(code: RecoveryCode | str) -> str:
    s = code.as_string() if isinstance(code, RecoveryCode) else " ".join(code.lower().split())
    return _PH.hash(s)


def verify_recovery_code(code: str, hash_: str) -> bool:
    normalized = " ".join(code.lower().split())
    try:
        return _PH.verify(hash_, normalized)
    except (VerifyMismatchError, Exception):
        return False
