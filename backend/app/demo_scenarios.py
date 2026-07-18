"""Synthetic, resettable judge scenarios. No real family data belongs here."""
from __future__ import annotations

from typing import Any

DEMO_VERSION = "guardian-review-demo-v1"

SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "id": "unknown-contact-secrecy",
        "title": "Unknown contact requesting secrecy and platform migration",
        "description": "An unknown contact asks a child to keep a chat secret and move platforms.",
        "text": "Don't tell your parents about this. Can we move to Discord and talk somewhere private?",
        "age_group": "10_13",
        "relationship_context": "unknown_person",
        "repeated_behavior": "no",
        "parent_goal": "prepare_conversation",
        "expected_local_severity": "critical",
    },
    {
        "id": "ambiguous-gaming-language",
        "title": "Ambiguous gaming conversation using alarming language",
        "description": "Competitive game chat uses a phrase that can be harassment or in-game slang.",
        "text": "That boss wiped us again. kys and respawn before the next round, lol.",
        "age_group": "14_17",
        "relationship_context": "known_peer",
        "repeated_behavior": "no",
        "parent_goal": "understand_context",
        "expected_local_severity": "medium",
    },
    {
        "id": "school-self-harm-research",
        "title": "School research involving self-harm terminology",
        "description": "A school assignment quotes alarming terminology without establishing personal intent.",
        "text": "Health class research notes: compare how news reports describe a suicide plan and prevention resources.",
        "age_group": "14_17",
        "relationship_context": "school_or_activity_contact",
        "repeated_behavior": "no",
        "parent_goal": "understand_context",
        "expected_local_severity": "critical",
    },
    {
        "id": "peer-coercion-repeated",
        "title": "Peer coercion and repeated pressure",
        "description": "A known peer repeatedly applies pressure and asks for secrecy.",
        "text": "Keep this a secret. Everyone will hate you if you refuse again. Send it tonight.",
        "age_group": "10_13",
        "relationship_context": "known_peer",
        "repeated_behavior": "yes",
        "parent_goal": "plan_follow_up",
        "expected_local_severity": "critical",
    },
    {
        "id": "benign-medical-discussion",
        "title": "Benign medical or educational discussion",
        "description": "Educational material mentions a controlled substance and should invite context.",
        "text": "Science worksheet: explain why fentanyl dosage is measured carefully in hospital settings.",
        "age_group": "14_17",
        "relationship_context": "school_or_activity_contact",
        "repeated_behavior": "no",
        "parent_goal": "understand_context",
        "expected_local_severity": "medium",
    },
    {
        "id": "harmless-control",
        "title": "Clearly harmless control scenario",
        "description": "A normal family logistics message verifies the no-rule-match path.",
        "text": "Practice ends at five. Please bring the blue water bottle and library book.",
        "age_group": "10_13",
        "relationship_context": "family_member",
        "repeated_behavior": "no",
        "parent_goal": "understand_context",
        "expected_local_severity": "none",
    },
)


def scenario_by_id(scenario_id: str) -> dict[str, Any] | None:
    return next((scenario for scenario in SCENARIOS if scenario["id"] == scenario_id), None)


def public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Return metadata for the UI without exposing the evidence before triggering it."""
    return {key: value for key, value in scenario.items() if key != "text"}
