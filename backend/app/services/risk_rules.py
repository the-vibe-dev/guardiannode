"""Deterministic safety rules.

Each rule has a regex (or list of regexes) and a severity. Multiple rules can
trigger; the result aggregates categories and severity.

These run before the LLM and provide both speed (matches < 10ms) and a
high-confidence floor for known-bad patterns the LLM might miss or soften.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

RULES_VERSION = "0.1.0"


@dataclass
class Rule:
    id: str
    category: str
    severity: str  # low | medium | high | critical
    patterns: list[re.Pattern[str]] = field(default_factory=list)
    description: str = ""
    confidence: float = 0.9


@dataclass
class RuleMatch:
    rule_id: str
    category: str
    severity: str
    confidence: float
    matched_text: str
    description: str


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_RULES: list[Rule] = [
    # ---- Critical ----------------------------------------------------------
    Rule(
        id="self_harm_imminent",
        category="self_harm",
        severity="critical",
        patterns=_compile([
            r"\bi\s+(?:want|am going|'m going)\s+to\s+(?:kill|hurt|harm)\s+myself\b",
            r"\bi\s+(?:want|am going|'m going)\s+to\s+(?:end|take)\s+(?:my\s+life|it\s+all)\b",
            r"\b(?:tonight|today)\s+(?:is|i'?m)\s+(?:my\s+last|going\s+to\s+kill)\b",
            r"\bsuicide\s+(?:plan|tonight|method)\b",
        ]),
        description="Imminent self-harm language",
        confidence=0.95,
    ),
    Rule(
        id="grooming_send_pic_minor_context",
        category="sexual_content",
        severity="critical",
        patterns=_compile([
            r"\b(?:send|share)\s+(?:me\s+)?(?:a\s+)?(?:pic|picture|photo|nude|nudes)\b",
            r"\bdick\s+pic\b",
            r"\bsend\s+me\s+(?:something|one)\s+(?:dirty|hot|sexy)\b",
        ]),
        description="Sexually explicit image request",
        confidence=0.9,
    ),
    Rule(
        id="threat_violence_credible",
        category="threat",
        severity="critical",
        patterns=_compile([
            r"\bi'?ll\s+kill\s+you\b",
            r"\bi(?:'m|\s+am)\s+going\s+to\s+kill\s+you\b",
            r"\b(?:bring|have)\s+(?:a|my)\s+gun\s+(?:to|tomorrow|today)\b",
            r"\bshoot\s+up\s+(?:the\s+)?school\b",
        ]),
        description="Credible threat of violence",
        confidence=0.85,
    ),
    Rule(
        id="grooming_secrecy_critical",
        category="secrecy_request",
        severity="critical",
        patterns=_compile([
            r"\bdon'?t\s+tell\s+(?:your\s+)?(?:parents|mom|dad|mum|family|anyone)\b",
            r"\bkeep\s+(?:this|us)\s+(?:a\s+)?secret\b",
            r"\bit\s+can\s+be\s+our\s+(?:little\s+)?secret\b",
        ]),
        description="Secrecy/coercion phrase",
        confidence=0.92,
    ),

    # ---- High ----------------------------------------------------------------
    Rule(
        id="off_platform_contact",
        category="off_platform_contact",
        severity="high",
        patterns=_compile([
            r"\badd\s+me\s+on\s+(?:snap|snapchat|insta|instagram|discord|whatsapp|telegram|kik)\b",
            r"\bmy\s+(?:snap|snapchat|discord|insta|kik)\s+is\b",
            r"\b(?:dm|message)\s+me\s+on\s+(?:discord|snap|insta|telegram)\b",
            r"\bcan\s+we\s+(?:talk|chat)\s+(?:on|somewhere)\s+(?:else|private)\b",
            r"\b(?:switch|move)\s+to\s+(?:discord|snap|whatsapp|telegram)\b",
        ]),
        description="Off-platform contact request",
        confidence=0.88,
    ),
    Rule(
        id="private_info_request",
        category="private_info_request",
        severity="high",
        patterns=_compile([
            r"\bwhat'?s?\s+your\s+(?:address|phone\s*number|home\s+address)\b",
            r"\bwhere\s+do\s+you\s+(?:live|go\s+to\s+school)\b",
            r"\bwhat\s+school\s+do\s+you\s+go\s+to\b",
            r"\bsend\s+me\s+your\s+(?:address|phone\s*number)\b",
        ]),
        description="Private info request",
        confidence=0.9,
    ),
    Rule(
        id="scam_robux_giftcard",
        category="scam",
        severity="high",
        patterns=_compile([
            r"\bfree\s+robux\b",
            r"\bfree\s+v[\-\s]?bucks\b",
            r"\bfree\s+gift\s+card\b",
            r"\b(?:i\s+can\s+|i'?ll\s+)?(?:give|hook)\s+you\s+(?:up\s+with\s+)?(?:free\s+)?robux\b",
            r"\bbuy\s+me\s+a\s+gift\s+card\b",
            r"\bsteam\s+wallet\s+code\b",
        ]),
        description="Robux/gift-card/money scam",
        confidence=0.88,
    ),
    Rule(
        id="phishing_link_shorteners",
        category="phishing",
        severity="high",
        patterns=_compile([
            r"\bbit\.ly/\S+",
            r"\btinyurl\.com/\S+",
            r"\bgoo\.gl/\S+",
            r"\b(?:click|tap)\s+this\s+link\b",
            r"\bverify\s+your\s+(?:account|password)\s+(?:here|now)\b",
        ]),
        description="Suspicious link",
        confidence=0.75,
    ),
    Rule(
        id="self_harm_phrases",
        category="self_harm",
        severity="high",
        patterns=_compile([
            r"\bi\s+(?:hate|cant\s+stand)\s+(?:my\s+)?life\b",
            r"\bi\s+want\s+to\s+(?:disappear|not\s+exist)\b",
            r"\beveryone\s+(?:would\s+be\s+better|hates\s+me)\b",
            r"\bcutting\s+(?:myself|again)\b",
        ]),
        description="Self-harm signal",
        confidence=0.78,
    ),
    Rule(
        id="age_question_in_chat",
        category="grooming",
        severity="high",
        patterns=_compile([
            r"\bhow\s+old\s+are\s+you\b",
            r"\bwhat'?s?\s+your\s+age\b",
            r"\ba/?s/?l\b",  # age/sex/location classic shorthand
        ]),
        description="Age question (potential grooming probe)",
        confidence=0.6,  # lower confidence — context matters a lot
    ),

    # ---- Medium --------------------------------------------------------------
    Rule(
        id="bullying_keywords",
        category="bullying",
        severity="medium",
        patterns=_compile([
            r"\b(?:kys|kill\s+yourself)\b",
            r"\b(?:nobody|no one)\s+(?:likes|loves)\s+you\b",
            r"\byou'?re\s+(?:worthless|trash|garbage|a\s+loser)\b",
            r"\b(?:everyone|the whole school)\s+hates\s+you\b",
        ]),
        description="Bullying/harassment keywords",
        confidence=0.85,
    ),
    Rule(
        id="drug_mentions",
        category="drugs",
        severity="medium",
        patterns=_compile([
            r"\b(?:cocaine|heroin|meth|fentanyl)\b",
            r"\b(?:smoke|hit)\s+(?:weed|a\s+blunt|a\s+joint)\b",
        ]),
        description="Drug reference",
        confidence=0.7,
    ),
    Rule(
        id="dangerous_challenge",
        category="dangerous_challenge",
        severity="medium",
        patterns=_compile([
            r"\btide\s+pod\s+challenge\b",
            r"\bblackout\s+challenge\b",
            r"\bbenadryl\s+challenge\b",
            r"\bskull\s+breaker\s+challenge\b",
        ]),
        description="Known dangerous social-media challenge",
        confidence=0.95,
    ),
]


def _compile_custom(phrases: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Compile parent-configured phrases into case-insensitive, whole-word
    regexes. Returns (original_phrase, pattern) pairs so the alert can quote
    the parent's exact phrase, not a regex.
    """
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for raw in phrases:
        phrase = (raw or "").strip()
        if not phrase or len(phrase) > 200:
            continue
        # Whole-word match for tokens; substring for multi-word phrases.
        if re.fullmatch(r"\w+", phrase):
            pat = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        else:
            pat = re.compile(re.escape(phrase), re.IGNORECASE)
        compiled.append((phrase, pat))
    return compiled


def evaluate(text: str, custom_phrases: list[str] | None = None) -> list[RuleMatch]:
    """Run all rules (and any parent-configured custom phrases) over the text.

    ``custom_phrases`` is a per-profile list of strings — child's real name,
    address, school, nicknames, anything the parent wants flagged. Each hit
    yields a RuleMatch with rule_id="custom_watch:<phrase>" at severity=high.
    """
    if not text:
        return []
    matches: list[RuleMatch] = []
    for rule in _RULES:
        for pattern in rule.patterns:
            m = pattern.search(text)
            if m:
                matches.append(
                    RuleMatch(
                        rule_id=rule.id,
                        category=rule.category,
                        severity=rule.severity,
                        confidence=rule.confidence,
                        matched_text=m.group(0),
                        description=rule.description,
                    )
                )
                break  # one match per rule is enough
    if custom_phrases:
        for phrase, pat in _compile_custom(custom_phrases):
            m = pat.search(text)
            if m:
                matches.append(
                    RuleMatch(
                        rule_id=f"custom_watch:{phrase.lower()}",
                        category="custom_watch",
                        severity="high",
                        confidence=0.95,
                        matched_text=m.group(0),
                        description=f"Parent-configured watch phrase: {phrase!r}",
                    )
                )
    return matches


SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def max_severity(matches: list[RuleMatch]) -> str:
    if not matches:
        return "none"
    return max(matches, key=lambda m: SEVERITY_ORDER[m.severity]).severity


def aggregated_categories(matches: list[RuleMatch]) -> list[str]:
    return sorted({m.category for m in matches})
