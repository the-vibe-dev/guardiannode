"""Durable Guardian Review workflow: preview, consent, execution, persistence."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.db.models import GuardianReview, GuardianReviewFeedback, GuardianReviewPreview, User
from app.guardian_review_models import (
    PROMPT_VERSION,
    REDACTION_VERSION,
    SCHEMA_VERSION,
    GuardianReviewAssessment,
    GuardianReviewContext,
    GuardianReviewOutboundPayload,
    GuidanceContextSnapshot,
    ModelUsage,
    ReviewAccepted,
    ReviewFeedbackRequest,
    ReviewFeedbackResponse,
    ReviewPreviewResponse,
    ReviewResult,
    ReviewStatus,
    ReviewSummary,
)
from app.services import encryption
from app.services import guardian_review_codex_auth as codex_auth
from app.services.audit import log_action
from app.services.guardian_review_minimization import InvalidIncidentError, build_minimized_incident
from app.services.guardian_review_providers import ProviderError, provider_for

RETENTION_NOTICES = {
    "mock": "No data leaves this device in mock mode.",
    "codex": "Data is sent to OpenAI through Codex and follows the connected ChatGPT plan or workspace data controls.",
    "openai": "Data is sent to the OpenAI Responses API with store=false. The administrator has marked this project as Zero Data Retention enabled; GuardianNode cannot independently verify the account setting.",
}
DISCLOSURES = {
    "mock": "Mock mode is local and deterministic. Nothing in this preview is sent to OpenAI.",
    "codex": "This exact preview will be sent to an external OpenAI model through the connected ChatGPT/Codex account. It is not represented as zero retention.",
    "openai": "This exact preview will be sent to an external OpenAI model through the Responses API. store=false is used, and verified account retention controls remain a separate requirement.",
}


class WorkflowError(ValueError):
    def __init__(self, code: str, *, status_code: int = 400):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _preview_aad(preview_id: str) -> bytes:
    return f"guardian-review-preview:{preview_id}".encode()


def _review_aad(review_id: str) -> bytes:
    return f"guardian-review-assessment:{review_id}".encode()


def _prompt(version: str) -> str:
    if version not in {"guardian-review-v1", "guardian-review-v2"}:
        raise WorkflowError("configuration_error", status_code=503)
    filename = f"{version.replace('-', '_')}.txt"
    return (Path(__file__).resolve().parents[1] / "prompts" / filename).read_text("utf-8")


def _settings():
    return settings_mod.settings


def configured_model(provider: str) -> str:
    if provider == "codex":
        return _settings().guardian_review_codex_model
    return _settings().guardian_review_model


def _ensure_enabled() -> None:
    if not _settings().guardian_review_enabled:
        raise WorkflowError("feature_disabled", status_code=503)


def provider_readiness(provider: str | None = None) -> dict[str, Any]:
    settings = _settings()
    selected = (provider or settings.guardian_review_provider).strip().lower()
    if not settings.guardian_review_enabled:
        return {"ready": False, "blocking_reason": "feature_disabled"}
    if selected == "mock":
        ready = bool(settings.dev_mode or settings.guardian_review_provider == "mock")
        return {"ready": ready, "blocking_reason": None if ready else "mock_not_available"}
    if selected == "openai":
        has_key = bool(settings.openai_api_key or os.getenv("OPENAI_API_KEY"))
        if not has_key:
            return {"ready": False, "blocking_reason": "provider_auth_required"}
        if not settings.guardian_review_zdr_confirmed:
            return {"ready": False, "blocking_reason": "zdr_not_confirmed"}
        return {"ready": True, "blocking_reason": None}
    if selected == "codex":
        status = codex_auth.status(
            executable=settings.codex_executable,
            codex_home=settings.codex_home_resolved,
        )
        return {
            "ready": False,
            "blocking_reason": "provider_unavailable",
            "security_hold": True,
            "provider_status": status,
        }
    return {"ready": False, "blocking_reason": "configuration_error"}


def _ensure_provider_ready(provider: str) -> None:
    readiness = provider_readiness(provider)
    if not readiness["ready"]:
        raise WorkflowError(str(readiness["blocking_reason"]), status_code=503)


def _audit_details(
    *,
    alert_id: str,
    provider: str,
    model: str,
    schema_version: str,
    prompt_version: str,
    redaction_version: str,
    information_categories: list[str],
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "incident_id": alert_id,
        "provider": provider,
        "model": model,
        "schema_version": schema_version,
        "prompt_version": prompt_version,
        "redaction_version": redaction_version,
        "information_categories": sorted(information_categories),
        "status": status,
        **extra,
    }


def create_preview(
    db: Session,
    *,
    alert_id: str,
    context: GuardianReviewContext,
    user: User,
) -> ReviewPreviewResponse:
    _ensure_enabled()
    provider = _settings().guardian_review_provider.strip().lower()
    if provider not in RETENTION_NOTICES:
        raise WorkflowError("configuration_error", status_code=503)
    _ensure_provider_ready(provider)
    schema_version = SCHEMA_VERSION
    prompt_version = _settings().guardian_review_prompt_version or PROMPT_VERSION
    try:
        incident = build_minimized_incident(
            db,
            alert_id=alert_id,
            context=context,
            schema_version=schema_version,
            prompt_version=prompt_version,
            provider=provider,
            model=configured_model(provider),
        )
    except InvalidIncidentError as exc:
        status_code = 413 if "size limit" in str(exc) else 404
        code = "payload_too_large" if status_code == 413 else "not_found"
        raise WorkflowError(code, status_code=status_code) from exc
    preview_id = uuid4().hex
    created_at = _now()
    expires_at = created_at + timedelta(seconds=_settings().guardian_review_preview_ttl_seconds)
    encrypted_record = {
        "context": context.model_dump(mode="json"),
        "outbound_payload": incident.payload,
        "redactions": incident.redactions,
    }
    row = GuardianReviewPreview(
        preview_id=preview_id,
        alert_id=alert_id,
        actor_user_id=user.id,
        provider=provider,
        model_requested=configured_model(provider),
        schema_version=schema_version,
        prompt_version=prompt_version,
        redaction_version=REDACTION_VERSION,
        information_categories=incident.information_categories,
        payload_digest=incident.digest,
        incident_fingerprint=incident.fingerprint,
        payload_enc=encryption.encrypt_bytes(_json_bytes(encrypted_record), aad=_preview_aad(preview_id)),
        fresh_assessment=context.fresh_assessment,
        created_at=created_at,
        expires_at=expires_at,
    )
    db.add(row)
    log_action(
        db,
        actor=str(user.id),
        action="guardian_review.previewed",
        target=alert_id,
        details={
            **_audit_details(
                alert_id=alert_id,
                provider=provider,
                model=row.model_requested,
                schema_version=schema_version,
                prompt_version=prompt_version,
                redaction_version=REDACTION_VERSION,
                information_categories=incident.information_categories,
                status="previewed",
                parent_action="preview",
            ),
            "preview_id": preview_id,
            "payload_digest": incident.digest,
            "outbound_character_count": len(json.dumps(incident.payload, ensure_ascii=False)),
            "redaction_types": incident.redactions,
        },
    )
    db.commit()
    return ReviewPreviewResponse(
        preview_id=preview_id,
        alert_id=alert_id,
        provider=provider,
        model_requested=row.model_requested,
        schema_version=schema_version,
        prompt_version=prompt_version,
        redaction_version=REDACTION_VERSION,
        outbound_payload=GuardianReviewOutboundPayload.model_validate(incident.payload),
        preview_digest=incident.digest,
        field_count=len(incident.payload),
        character_count=len(json.dumps(incident.payload, ensure_ascii=False)),
        redactions_applied=incident.redactions,
        information_categories=incident.information_categories,
        external_processing=provider != "mock",
        disclosure=DISCLOSURES[provider],
        retention_notice=RETENTION_NOTICES[provider],
        expires_at=expires_at,
    )


def _load_preview_payload(row: GuardianReviewPreview) -> dict[str, Any]:
    if not row.payload_enc:
        raise WorkflowError("preview_stale", status_code=409)
    try:
        raw = encryption.decrypt_bytes(row.payload_enc, aad=_preview_aad(row.preview_id))
        value = json.loads(raw)
    except Exception as exc:
        raise WorkflowError("preview_stale", status_code=409) from exc
    if not isinstance(value, dict):
        raise WorkflowError("preview_stale", status_code=409)
    return value


def submit_review(
    db: Session,
    *,
    alert_id: str,
    preview_id: str,
    preview_digest: str,
    user: User,
) -> ReviewAccepted:
    _ensure_enabled()
    preview = db.get(GuardianReviewPreview, preview_id)
    if preview is None or preview.actor_user_id != user.id or preview.alert_id != alert_id:
        raise WorkflowError("not_found", status_code=404)
    if preview.provider != _settings().guardian_review_provider.strip().lower():
        raise WorkflowError("preview_stale", status_code=409)
    _ensure_provider_ready(preview.provider)
    if preview.review_id:
        existing = db.get(GuardianReview, preview.review_id)
        if existing:
            return ReviewAccepted(review_id=existing.review_id, status=cast(ReviewStatus, existing.status), status_url=f"/api/guardian-reviews/{existing.review_id}")
    if _aware(preview.expires_at) <= _now():
        raise WorkflowError("preview_expired", status_code=409)
    if not hmac.compare_digest(preview.payload_digest, preview_digest):
        raise WorkflowError("preview_stale", status_code=409)
    stored = _load_preview_payload(preview)
    try:
        context = GuardianReviewContext.model_validate(stored["context"])
        incident = build_minimized_incident(
            db,
            alert_id=preview.alert_id,
            context=context,
            schema_version=preview.schema_version,
            prompt_version=preview.prompt_version,
            provider=preview.provider,
            model=preview.model_requested,
        )
    except Exception as exc:
        raise WorkflowError("preview_stale", status_code=409) from exc
    if (
        preview.redaction_version != REDACTION_VERSION
        or not hmac.compare_digest(incident.digest, preview.payload_digest)
        or not hmac.compare_digest(incident.fingerprint, preview.incident_fingerprint)
    ):
        raise WorkflowError("preview_stale", status_code=409)
    base_key = f"{preview.alert_id}:{preview.payload_digest}:{preview.provider}:{preview.model_requested}:{preview.schema_version}:{preview.prompt_version}:{preview.redaction_version}"
    if preview.fresh_assessment:
        base_key += f":fresh:{preview.preview_id}"
    dedup_key = hashlib.sha256(base_key.encode()).hexdigest()
    existing = db.query(GuardianReview).filter(GuardianReview.dedup_key == dedup_key).first()
    if existing:
        preview.review_id = existing.review_id
        preview.consumed_at = _now()
        db.commit()
        return ReviewAccepted(review_id=existing.review_id, status=cast(ReviewStatus, existing.status), status_url=f"/api/guardian-reviews/{existing.review_id}")
    review_id = uuid4().hex
    row = GuardianReview(
        review_id=review_id,
        preview_id=preview.preview_id,
        alert_id=preview.alert_id,
        requester_user_id=user.id,
        status="queued",
        provider=preview.provider,
        dedup_key=dedup_key,
        schema_version=preview.schema_version,
        prompt_version=preview.prompt_version,
        redaction_version=preview.redaction_version,
        model_requested=preview.model_requested,
    )
    db.add(row)
    preview.review_id = review_id
    preview.consumed_at = _now()
    base_audit = _audit_details(
        alert_id=preview.alert_id,
        provider=row.provider,
        model=row.model_requested,
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        redaction_version=row.redaction_version,
        information_categories=list(preview.information_categories or []),
        status="queued",
    )
    log_action(db, actor=str(user.id), action="guardian_review.consented", target=review_id, details={**base_audit, "parent_action": "consent", "preview_id": preview.preview_id, "payload_digest": preview.payload_digest})
    log_action(db, actor=str(user.id), action="guardian_review.queued", target=review_id, details=base_audit)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(GuardianReview).filter(GuardianReview.dedup_key == dedup_key).one()
        return ReviewAccepted(review_id=existing.review_id, status=cast(ReviewStatus, existing.status), status_url=f"/api/guardian-reviews/{existing.review_id}")
    return ReviewAccepted(review_id=review_id, status="queued", status_url=f"/api/guardian-reviews/{review_id}")


def get_result(db: Session, *, review_id: str, user: User) -> ReviewResult:
    row = db.get(GuardianReview, review_id)
    if row is None or (user.role != "admin" and row.requester_user_id != user.id):
        raise WorkflowError("not_found", status_code=404)
    assessment = None
    if row.assessment_enc:
        try:
            assessment = GuardianReviewAssessment.model_validate_json(
                encryption.decrypt_bytes(row.assessment_enc, aad=_review_aad(row.review_id))
            )
        except Exception:
            raise WorkflowError("invalid_model_output", status_code=500) from None
    log_action(
        db,
        actor=str(user.id),
        action="guardian_review.viewed",
        target=review_id,
        details={"incident_id": row.alert_id, "status": row.status},
    )
    db.commit()
    error = None if not row.error_code else {"code": row.error_code, "message": _error_message(row.error_code), "retryable": row.error_code in {"upstream_timeout", "upstream_unavailable", "rate_limited", "database_busy"}, "review_id": row.review_id}
    usage_values = (
        row.input_tokens,
        row.cached_input_tokens,
        row.output_tokens,
        row.reasoning_tokens,
        row.total_tokens,
    )
    usage = ModelUsage(
        input_tokens=row.input_tokens,
        cached_input_tokens=row.cached_input_tokens,
        output_tokens=row.output_tokens,
        reasoning_tokens=row.reasoning_tokens,
        total_tokens=row.total_tokens,
    ) if any(value is not None for value in usage_values) else None
    guidance_context = _guidance_context(db.get(GuardianReviewPreview, row.preview_id))
    return ReviewResult(
        review_id=row.review_id,
        alert_id=row.alert_id,
        status=cast(ReviewStatus, row.status),
        provider=row.provider,
        created_at=row.created_at,
        completed_at=row.completed_at,
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        model_requested=row.model_requested,
        model_returned=row.model_returned,
        latency_ms=row.latency_ms,
        usage=usage,
        guidance_context=guidance_context,
        redaction_version=row.redaction_version,
        deleted_at=row.deleted_at,
        assessment=assessment,
        error=error,
    )


def _guidance_context(preview: GuardianReviewPreview | None) -> GuidanceContextSnapshot | None:
    if preview is None or preview.payload_enc is None:
        return None
    try:
        stored = _load_preview_payload(preview)
        context = GuardianReviewContext.model_validate(stored.get("context"))
        outbound = GuardianReviewOutboundPayload.model_validate(stored.get("outbound_payload"))
    except Exception:
        return None
    return GuidanceContextSnapshot(
        approximate_child_age_group=outbound.approximate_child_age_group,
        relationship_context=context.relationship_context,
        repeated_behavior=context.repeated_behavior,
        parent_believes_immediate_danger=context.parent_believes_immediate_danger,
        parent_goal=context.parent_goal,
    )


def _authorized_review(db: Session, review_id: str, user: User) -> GuardianReview:
    row = db.get(GuardianReview, review_id)
    if row is None or (user.role != "admin" and row.requester_user_id != user.id):
        raise WorkflowError("not_found", status_code=404)
    return row


def get_feedback(db: Session, *, review_id: str, user: User) -> ReviewFeedbackResponse | None:
    _authorized_review(db, review_id, user)
    row = db.query(GuardianReviewFeedback).filter(
        GuardianReviewFeedback.review_id == review_id,
        GuardianReviewFeedback.user_id == user.id,
    ).first()
    return _feedback_response(row) if row else None


def put_feedback(
    db: Session,
    *,
    review_id: str,
    request: ReviewFeedbackRequest,
    user: User,
) -> ReviewFeedbackResponse:
    review = _authorized_review(db, review_id, user)
    if review.status != "completed" or review.assessment_enc is None:
        raise WorkflowError("feedback_unavailable", status_code=409)
    labels = sorted(set(request.labels))
    row = db.query(GuardianReviewFeedback).filter(
        GuardianReviewFeedback.review_id == review_id,
        GuardianReviewFeedback.user_id == user.id,
    ).first()
    if row is None:
        row = GuardianReviewFeedback(
            feedback_id=uuid4().hex,
            review_id=review_id,
            user_id=user.id,
            created_at=_now(),
        )
        db.add(row)
    row.labels = labels
    row.schema_version = review.schema_version
    row.prompt_version = review.prompt_version
    row.redaction_version = review.redaction_version
    row.model = review.model_returned or review.model_requested
    row.updated_at = _now()
    log_action(
        db,
        actor=str(user.id),
        action="guardian_review.feedback",
        target=review_id,
        details={
            "incident_id": review.alert_id,
            "labels": labels,
            "schema_version": review.schema_version,
            "prompt_version": review.prompt_version,
            "redaction_version": review.redaction_version,
            "model": row.model,
            "local_only": True,
            "training_use": False,
        },
    )
    db.commit()
    return _feedback_response(row)


def _feedback_response(row: GuardianReviewFeedback) -> ReviewFeedbackResponse:
    return ReviewFeedbackResponse(
        review_id=row.review_id,
        labels=row.labels,
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        redaction_version=row.redaction_version,
        model=row.model,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def cancel_preview(db: Session, *, preview_id: str, user: User) -> None:
    preview = db.get(GuardianReviewPreview, preview_id)
    if preview is None or (user.role != "admin" and preview.actor_user_id != user.id):
        raise WorkflowError("not_found", status_code=404)
    if preview.review_id or preview.consumed_at:
        raise WorkflowError("cannot_cancel", status_code=409)
    details = _audit_details(
        alert_id=preview.alert_id,
        provider=preview.provider,
        model=preview.model_requested,
        schema_version=preview.schema_version,
        prompt_version=preview.prompt_version,
        redaction_version=preview.redaction_version,
        information_categories=list(preview.information_categories or []),
        status="cancelled",
        parent_action="cancel",
        preview_id=preview.preview_id,
    )
    db.delete(preview)
    log_action(db, actor=str(user.id), action="guardian_review.cancelled", target=preview.alert_id, details=details)
    db.commit()


def list_reviews(
    db: Session,
    *,
    user: User,
    alert_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[ReviewSummary]:
    query = db.query(GuardianReview).order_by(GuardianReview.created_at.desc())
    if user.role != "admin":
        query = query.filter(GuardianReview.requester_user_id == user.id)
    if alert_id:
        query = query.filter(GuardianReview.alert_id == alert_id)
    if status:
        query = query.filter(GuardianReview.status == status)
    return [_summary(row) for row in query.limit(limit).all()]


def _summary(row: GuardianReview) -> ReviewSummary:
    return ReviewSummary(
        review_id=row.review_id,
        alert_id=row.alert_id,
        status=cast(ReviewStatus, row.status),
        provider=row.provider,
        model_requested=row.model_requested,
        model_returned=row.model_returned,
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        redaction_version=row.redaction_version,
        created_at=row.created_at,
        completed_at=row.completed_at,
        deleted_at=row.deleted_at,
        latency_ms=row.latency_ms,
        has_assessment=bool(row.assessment_enc),
    )


def delete_review(db: Session, *, review_id: str, user: User) -> ReviewSummary:
    row = db.get(GuardianReview, review_id)
    if row is None or (user.role != "admin" and row.requester_user_id != user.id):
        raise WorkflowError("not_found", status_code=404)
    if row.status in {"queued", "running"}:
        raise WorkflowError("review_in_progress", status_code=409)
    if row.status == "deleted":
        return _summary(row)
    db.query(GuardianReviewFeedback).filter(
        GuardianReviewFeedback.review_id == row.review_id
    ).delete(synchronize_session=False)
    preview = db.get(GuardianReviewPreview, row.preview_id)
    information_categories = list(preview.information_categories or []) if preview else []
    row.assessment_enc = None
    row.provider_response_id = None
    row.error_code = None
    row.dedup_key = hashlib.sha256(f"{row.dedup_key}:deleted:{row.review_id}".encode()).hexdigest()
    row.status = "deleted"
    row.deleted_at = _now()
    if preview:
        preview.payload_enc = None
        preview.expires_at = _now()
    log_action(
        db,
        actor=str(user.id),
        action="guardian_review.deleted",
        target=row.review_id,
        details=_audit_details(
            alert_id=row.alert_id,
            provider=row.provider,
            model=row.model_requested,
            schema_version=row.schema_version,
            prompt_version=row.prompt_version,
            redaction_version=row.redaction_version,
            information_categories=information_categories,
            status="deleted",
            parent_action="delete_local_assessment",
        ),
    )
    db.commit()
    return _summary(row)


def _error_message(code: str) -> str:
    return {
        "feature_disabled": "Guardian Review is disabled until it is configured.",
        "provider_auth_required": "The selected provider is not connected.",
        "provider_unavailable": "The selected Guardian Review provider is unavailable.",
        "zdr_not_confirmed": "OpenAI API mode requires confirmed Zero Data Retention.",
        "upstream_timeout": "Guardian Review timed out.",
        "upstream_unavailable": "Guardian Review is temporarily unavailable.",
        "rate_limited": "Guardian Review is temporarily rate limited.",
        "upstream_refusal": "The model declined this assessment.",
        "upstream_policy_or_validation": "The provider rejected the request.",
        "invalid_model_output": "The model returned an invalid structured assessment.",
        "configuration_error": "Guardian Review is not configured correctly.",
        "cannot_cancel": "This preview can no longer be cancelled.",
        "review_in_progress": "Wait for this Guardian Review to finish before deleting it.",
        "payload_too_large": "The minimized incident is still too large to send safely.",
        "feedback_unavailable": "Feedback is available after a completed Guardian Review.",
        "database_busy": "GuardianNode is busy saving another update. Your incident is safe; try again shortly.",
    }.get(code, "Guardian Review failed safely.")


async def process_one(db: Session, *, provider_override=None, sleep=asyncio.sleep) -> bool:
    row = db.query(GuardianReview).filter(GuardianReview.status == "queued").order_by(GuardianReview.created_at).first()
    if row is None:
        return False
    row.status = "running"
    row.started_at = _now()
    row.error_code = None
    db.commit()
    preview = db.get(GuardianReviewPreview, row.preview_id)
    if preview is None:
        _fail(db, row, "preview_stale")
        return True
    try:
        stored = _load_preview_payload(preview)
    except WorkflowError as exc:
        _fail(db, row, exc.code)
        return True
    payload = stored.get("outbound_payload")
    if not isinstance(payload, dict):
        _fail(db, row, "preview_stale")
        return True
    try:
        provider = provider_override or provider_for(_settings(), provider_name=row.provider)
    except ProviderError as exc:
        _fail(db, row, exc.code)
        return True
    max_attempts = max(1, min(3, int(_settings().guardian_review_max_attempts)))
    audit_base = _audit_details(
        alert_id=row.alert_id,
        provider=row.provider,
        model=row.model_requested,
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        redaction_version=row.redaction_version,
        information_categories=list(preview.information_categories or []),
        status="sent",
    )
    for attempt in range(1, max_attempts + 1):
        row.attempts = attempt
        log_action(db, actor="system", action="guardian_review.sent", target=row.review_id, details={**audit_base, "attempt": attempt})
        db.commit()
        try:
            result = await provider.assess(payload=payload, prompt=_prompt(row.prompt_version), model=row.model_requested, timeout=float(_settings().guardian_review_timeout_seconds))
            row.assessment_enc = encryption.encrypt_bytes(result.assessment.model_dump_json().encode(), aad=_review_aad(row.review_id))
            row.model_returned = result.model_returned
            row.provider_response_id = result.response_id
            row.latency_ms = result.latency_ms
            if result.usage:
                row.input_tokens = result.usage.input_tokens
                row.cached_input_tokens = result.usage.cached_input_tokens
                row.output_tokens = result.usage.output_tokens
                row.reasoning_tokens = result.usage.reasoning_tokens
                row.total_tokens = result.usage.total_tokens
            row.status = "completed"
            row.completed_at = _now()
            log_action(db, actor="system", action="guardian_review.completed", target=row.review_id, details={**audit_base, "model_returned": row.model_returned, "attempts": row.attempts, "latency_ms": row.latency_ms, "total_tokens": row.total_tokens, "status": row.status})
            db.commit()
            return True
        except ProviderError as exc:
            if not exc.retryable or attempt >= max_attempts:
                _fail(db, row, exc.code)
                return True
            await sleep(exc.retry_after if exc.retry_after is not None else random.uniform(1.0, 3.0))
        except Exception:
            _fail(db, row, "upstream_unavailable")
            return True
    return True


def _fail(db: Session, row: GuardianReview, code: str) -> None:
    row.status = "failed"
    row.error_code = code
    row.completed_at = _now()
    if row.started_at:
        row.latency_ms = max(0, int((_now() - _aware(row.started_at)).total_seconds() * 1000))
    preview = db.get(GuardianReviewPreview, row.preview_id)
    log_action(
        db,
        actor="system",
        action="guardian_review.failed",
        target=row.review_id,
        details={
            **_audit_details(
                alert_id=row.alert_id,
                provider=row.provider,
                model=row.model_requested,
                schema_version=row.schema_version,
                prompt_version=row.prompt_version,
                redaction_version=row.redaction_version,
                information_categories=list(preview.information_categories or []) if preview else [],
                status=row.status,
            ),
            "attempts": row.attempts,
            "error_code": code,
        },
    )
    db.commit()


def recover_stale_jobs(db: Session, *, older_than_seconds: int = 120) -> int:
    cutoff = _now() - timedelta(seconds=older_than_seconds)
    rows = db.query(GuardianReview).filter(GuardianReview.status == "running", GuardianReview.started_at < cutoff).all()
    for row in rows:
        row.status = "queued"
        row.started_at = None
    if rows:
        db.commit()
    return len(rows)
