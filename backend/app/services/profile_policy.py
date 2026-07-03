"""Per-child policy: privacy, alert thresholds, and capture aggressiveness.

The point is to let a parent give an older kid real privacy while still catching
the things that matter. A 16-year-old swearing or trading trash talk isn't an
alert; a private chat with a boyfriend/girlfriend stays private — unless it turns
into something serious. But self-harm, grooming, threats, and the parent's own
watch phrases (name/address/school) are PROTECTED: they always alert, at every
age. You can't accidentally silence the things that keep a kid safe.

Each category has a mode:
  - "alert"   : surface it as an alert and (per severity) notify the parent
  - "monitor" : record it quietly in the feed, no notification — parent can look
                if they want, but the kid isn't being pinged on
  - "allow"   : ignore it entirely

…plus an optional per-category minimum severity ("private unless serious": set
sexual_content to alert only at `critical`).

Capture level controls how much the agent grabs:
  - "tight"    : frequent capture, catches small changes (least privacy)
  - "balanced" : default
  - "leeway"   : infrequent, only meaningful scene changes (most privacy)
"""
from __future__ import annotations

from dataclasses import dataclass

SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# Always alert at the detected severity, regardless of age/privacy settings.
# These are the child-safety floor (see docs/SAFETY_BOUNDARIES.md) and the
# parent's own watch phrases (they explicitly chose those).
PROTECTED_CATEGORIES = {
    "self_harm", "grooming", "threat", "sexual_exploitation",
    "child_sexual_content", "custom_watch",
}

# Categories the parent can tune, with friendly labels for the dashboard.
TUNABLE_CATEGORIES = [
    ("bullying", "Bullying / mean messages"),
    ("profanity", "Swearing / profanity"),
    ("sexual_content", "Sexual or romantic talk (peers)"),
    ("nudity", "Nudity / explicit images"),
    ("drugs", "Drugs / alcohol references"),
    ("weapons", "Weapons"),
    ("gore", "Gore / graphic violence"),
    ("scam", "Scams"),
    ("phishing", "Phishing"),
    ("off_platform_contact", "Off-platform contact requests"),
    ("private_info_visible", "Personal info shared on screen"),
    ("hate_symbol", "Hate symbols / slurs"),
    ("unknown_link", "Unknown / suspicious links"),
]

CAPTURE_LEVELS = {
    # max_capture_interval_seconds is the unchanged-screen safety resend; keep
    # it slower than backend vision classification on standalone GPUs.
    "tight": {
        "cadence_seconds": 4,
        "phash_threshold": 2,
        "full_screen_change_threshold": 8,
        "max_capture_interval_seconds": 60,
    },
    "balanced": {
        "cadence_seconds": 8,
        "phash_threshold": 3,
        "full_screen_change_threshold": 12,
        "max_capture_interval_seconds": 120,
    },
    "leeway": {
        "cadence_seconds": 15,
        "phash_threshold": 5,
        "full_screen_change_threshold": 18,
        "max_capture_interval_seconds": 300,
    },
}

VALID_MODES = {"alert", "monitor", "allow"}


def _cats(pairs: dict[str, tuple[str, str | None]]) -> dict:
    """Helper: {category: (mode, min_severity)} -> policy category dict."""
    return {c: {"mode": m, "min_severity": s} for c, (m, s) in pairs.items()}


def default_policy_for_age(age_group: str) -> dict:
    """Sensible starting policy per age. The parent can adjust any of it."""
    if age_group == "under_10":
        # Youngest: minimal privacy, alert broadly.
        return {
            "min_severity": "low",
            "capture": {"level": "tight"},
            "categories": _cats({
                "profanity": ("alert", "low"),
                "bullying": ("alert", "low"),
                "sexual_content": ("alert", "low"),
                "nudity": ("alert", "low"),
                "drugs": ("alert", "low"),
                "off_platform_contact": ("alert", "low"),
            }),
        }
    if age_group == "14_17":
        # Oldest: privacy-forward. Swearing/trash talk is normal; romantic chat is
        # private unless it gets serious. Safety categories still always alert.
        return {
            "min_severity": "high",
            "capture": {"level": "leeway"},
            "categories": _cats({
                "profanity": ("allow", None),
                "bullying": ("monitor", "high"),
                "sexual_content": ("alert", "critical"),   # private unless serious
                "nudity": ("alert", "high"),
                "drugs": ("monitor", "high"),
                "weapons": ("alert", "high"),
                "off_platform_contact": ("alert", "high"),
                "scam": ("alert", "high"),
                "phishing": ("alert", "high"),
                "private_info_visible": ("alert", "high"),
            }),
        }
    # 10_13 (and default): moderate balance.
    return {
        "min_severity": "medium",
        "capture": {"level": "balanced"},
        "categories": _cats({
            "profanity": ("monitor", "medium"),
            "bullying": ("alert", "medium"),
            "sexual_content": ("alert", "high"),
            "nudity": ("alert", "medium"),
            "drugs": ("alert", "medium"),
            "off_platform_contact": ("alert", "medium"),
            "scam": ("alert", "medium"),
        }),
    }


def normalize(policy: dict | None, age_group: str = "10_13") -> dict:
    """Fill in a policy from the age default where keys are missing."""
    base = default_policy_for_age(age_group)
    if not policy:
        return base
    out = dict(base)
    if policy.get("min_severity") in SEVERITY_ORDER:
        out["min_severity"] = policy["min_severity"]
    if isinstance(policy.get("capture"), dict):
        out["capture"] = {**base["capture"], **policy["capture"]}
    if isinstance(policy.get("categories"), dict):
        out["categories"] = {**base["categories"], **policy["categories"]}
    return out


@dataclass
class Decision:
    create_alert: bool   # surface in the Risk Feed at all
    notify: bool         # send email/webhook
    reason: str


def decide(policy: dict, severity: str, categories: list[str]) -> Decision:
    """Apply the policy to one classification result."""
    sev = SEVERITY_ORDER.get(severity, 0)
    cats = categories or []

    # Protected categories always alert + notify at their detected severity.
    if any(c in PROTECTED_CATEGORIES for c in cats):
        return Decision(True, severity in ("high", "critical"), "protected_category")

    cat_settings = policy.get("categories", {})
    global_floor = SEVERITY_ORDER.get(policy.get("min_severity", "medium"), 2)

    want_alert = False
    want_monitor = False
    considered = cats or ["_uncategorized"]
    for c in considered:
        cs = cat_settings.get(c, {"mode": "alert"})
        mode = cs.get("mode", "alert")
        if mode == "allow":
            continue
        floor = SEVERITY_ORDER.get(cs.get("min_severity") or policy.get("min_severity", "medium"), global_floor)
        effective_floor = max(floor, global_floor)
        if sev < effective_floor:
            continue
        if mode == "monitor":
            want_monitor = True
        else:
            want_alert = True

    if want_alert:
        return Decision(True, severity in ("high", "critical"), "category_alert")
    if want_monitor:
        return Decision(True, False, "monitored")
    return Decision(False, False, "below_policy")


def capture_settings(policy: dict, age_group: str = "10_13") -> dict:
    """Resolve concrete agent capture knobs from the policy's capture section."""
    pol = normalize(policy, age_group)
    cap = pol.get("capture", {})
    level = cap.get("level", "balanced")
    base = dict(CAPTURE_LEVELS.get(level, CAPTURE_LEVELS["balanced"]))
    # Explicit overrides win over the level preset.
    for k in (
        "cadence_seconds",
        "phash_threshold",
        "full_screen_change_threshold",
        "max_capture_interval_seconds",
    ):
        if isinstance(cap.get(k), (int, float)):
            base[k] = int(cap[k])
    base["level"] = level
    base["full_screen_capture_enabled"] = bool(cap.get("full_screen_capture_enabled", True))
    return base
