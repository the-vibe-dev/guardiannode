"""Versioned, strict Guardian Review input and output contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.1.0"
PROMPT_VERSION = "guardian-review-v1"

Category = Literal[
    "none", "self_harm", "grooming", "sexual_content", "sexual_exploitation",
    "child_sexual_content", "nudity", "bullying", "threat", "scam", "phishing",
    "private_info", "private_info_request", "private_info_visible", "off_platform_contact",
    "secrecy_request", "drugs", "weapons", "gore", "hate_symbol", "dangerous_challenge",
    "profanity", "unknown_link", "custom_watch", "monitoring_gap", "unknown",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupportingEvidence(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    observation: str = Field(min_length=1, max_length=1000)
    relevance: str = Field(min_length=1, max_length=1000)


class RecommendedTone(StrictModel):
    tone: Literal["calm_and_curious", "supportive_and_direct", "urgent_and_reassuring", "safety_first"]
    rationale: str = Field(min_length=1, max_length=1000)


class ImmediateAction(StrictModel):
    priority: Literal["now", "today", "when_practical"]
    action: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=1000)


class FollowUpAction(StrictModel):
    timeframe: Literal["within_24_hours", "within_one_week", "ongoing"]
    action: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=1000)


GuidanceItem = Annotated[str, Field(min_length=1, max_length=1000)]
Guidance = list[GuidanceItem]
EvidenceId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:_-]+$")]


class GuardianReviewAssessment(StrictModel):
    schema_version: Literal["1.1.0"]
    assessment: Literal["concerning", "ambiguous", "likely_benign"]
    category: Category
    severity: Literal["none", "low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    plain_language_summary: str = Field(min_length=1, max_length=2000)
    observed_facts: Guidance = Field(max_length=10)
    inferences: Guidance = Field(max_length=10)
    supporting_evidence: list[SupportingEvidence] = Field(max_length=10)
    possible_benign_explanations: Guidance = Field(max_length=10)
    missing_context: Guidance = Field(max_length=10)
    questions_parent_should_answer: Guidance = Field(max_length=10)
    recommended_parent_tone: RecommendedTone
    suggested_opening_language: str = Field(min_length=1, max_length=1500)
    questions_to_ask_child: Guidance = Field(max_length=10)
    phrases_or_approaches_to_avoid: Guidance = Field(max_length=10)
    immediate_actions: list[ImmediateAction] = Field(max_length=10)
    follow_up_actions: list[FollowUpAction] = Field(max_length=10)
    escalation_indicators: Guidance = Field(max_length=10)
    limitations: Guidance = Field(min_length=1, max_length=10)


class GuardianReviewContext(StrictModel):
    relationship_context: Literal[
        "unknown_person", "known_peer", "known_adult", "family_member",
        "school_or_activity_contact", "other", "unknown",
    ] = "unknown"
    repeated_behavior: Literal["yes", "no", "unknown"] = "unknown"
    parent_believes_immediate_danger: bool = False
    parent_goal: Literal[
        "understand_context", "assess_urgency", "prepare_conversation", "plan_follow_up", "other",
    ] = "understand_context"
    parent_goal_details: str | None = Field(default=None, max_length=500)
    parent_context: str | None = Field(default=None, max_length=4000)
    selected_evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=20)
    fresh_assessment: bool = False


class ReviewPreviewResponse(StrictModel):
    preview_id: str
    alert_id: str
    provider: str
    model_requested: str
    schema_version: str
    prompt_version: str
    outbound_payload: dict
    preview_digest: str
    field_count: int
    character_count: int
    redactions_applied: list[str]
    retention_notice: str
    expires_at: datetime


class ReviewSubmitRequest(StrictModel):
    preview_id: str = Field(min_length=1, max_length=64)
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    consent: Literal[True]


class ReviewAccepted(StrictModel):
    review_id: str
    status: Literal["queued", "running", "completed", "failed"]
    status_url: str


class ReviewResult(StrictModel):
    review_id: str
    alert_id: str
    status: Literal["queued", "running", "completed", "failed"]
    provider: str
    created_at: datetime
    completed_at: datetime | None
    schema_version: str
    prompt_version: str
    model_requested: str
    model_returned: str | None
    latency_ms: int | None
    assessment: GuardianReviewAssessment | None
    error: dict | None


def strict_output_schema() -> dict:
    """Return the provider schema with strict object closure at every level."""
    return GuardianReviewAssessment.model_json_schema()
