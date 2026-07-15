"""Durable Guardian Review workflow: preview, consent, execution, persistence."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.db.models import GuardianReview, GuardianReviewPreview, User
from app.guardian_review_models import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    GuardianReviewAssessment,
    GuardianReviewContext,
    ReviewAccepted,
    ReviewPreviewResponse,
    ReviewResult,
)
from app.services import encryption
from app.services.audit import log_action
from app.services.guardian_review_minimization import (
    InvalidIncidentError,
    build_minimized_incident,
)
from app.services.guardian_review_providers import ProviderError, provider_for

RETENTION_NOTICES = {
    "mock": "No data leaves this device in mock mode.",
    "codex": "Data is sent through Codex under the connected ChatGPT plan or workspace data controls.",
    "openai": "Data is sent to the OpenAI Responses API with store=false; this deployment requires confirmed Zero Data Retention.",
}
ReviewStatus = Literal["queued", "running", "completed", "failed"]


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


def _prompt() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "guardian_review_v1.txt").read_text("utf-8")


def _settings():
    return settings_mod.settings


def configured_model(provider: str) -> str:
    if provider == "codex":
        return _settings().guardian_review_codex_model
    return _settings().guardian_review_model


def _ensure_enabled() -> None:
    if not _settings().guardian_review_enabled:
        raise WorkflowError("feature_disabled", status_code=503)


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
        raise WorkflowError("not_found", status_code=404) from exc
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
            "preview_id": preview_id,
            "provider": provider,
            "model": row.model_requested,
            "schema_version": schema_version,
            "prompt_version": prompt_version,
            "payload_digest": incident.digest,
            "field_names": sorted(incident.payload),
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
        outbound_payload=incident.payload,
        preview_digest=incident.digest,
        field_count=len(incident.payload),
        character_count=len(json.dumps(incident.payload, ensure_ascii=False)),
        redactions_applied=incident.redactions,
        retention_notice=RETENTION_NOTICES[provider],
        expires_at=expires_at,
    )


def _load_preview_payload(row: GuardianReviewPreview) -> dict[str, Any]:
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
    if not hmac.compare_digest(incident.digest, preview.payload_digest) or not hmac.compare_digest(incident.fingerprint, preview.incident_fingerprint):
        raise WorkflowError("preview_stale", status_code=409)
    base_key = f"{preview.alert_id}:{preview.payload_digest}:{preview.provider}:{preview.model_requested}:{preview.schema_version}:{preview.prompt_version}"
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
        model_requested=preview.model_requested,
    )
    db.add(row)
    preview.review_id = review_id
    preview.consumed_at = _now()
    log_action(db, actor=str(user.id), action="guardian_review.consented", target=review_id, details={"alert_id": preview.alert_id, "preview_id": preview.preview_id, "payload_digest": preview.payload_digest})
    log_action(db, actor=str(user.id), action="guardian_review.queued", target=review_id, details={"provider": row.provider, "model": row.model_requested, "schema_version": row.schema_version, "prompt_version": row.prompt_version})
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
    log_action(db, actor=str(user.id), action="guardian_review.viewed", target=review_id, details={"status": row.status})
    db.commit()
    error = None if not row.error_code else {"code": row.error_code, "message": _error_message(row.error_code), "retryable": row.error_code in {"upstream_timeout", "upstream_unavailable", "rate_limited"}, "review_id": row.review_id}
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
        assessment=assessment,
        error=error,
    )


def _error_message(code: str) -> str:
    return {
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
    for attempt in range(1, max_attempts + 1):
        row.attempts = attempt
        log_action(db, actor="system", action="guardian_review.sent", target=row.review_id, details={"provider": row.provider, "model": row.model_requested, "schema_version": row.schema_version, "prompt_version": row.prompt_version, "attempt": attempt})
        db.commit()
        try:
            result = await provider.assess(payload=payload, prompt=_prompt(), model=row.model_requested, timeout=float(_settings().guardian_review_timeout_seconds))
            row.assessment_enc = encryption.encrypt_bytes(result.assessment.model_dump_json().encode(), aad=_review_aad(row.review_id))
            row.model_returned = result.model_returned
            row.provider_response_id = result.response_id
            row.latency_ms = result.latency_ms
            row.status = "completed"
            row.completed_at = _now()
            log_action(db, actor="system", action="guardian_review.completed", target=row.review_id, details={"provider": row.provider, "model_requested": row.model_requested, "model_returned": row.model_returned, "schema_version": row.schema_version, "prompt_version": row.prompt_version, "attempts": row.attempts, "latency_ms": row.latency_ms, "status": row.status})
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
    log_action(db, actor="system", action="guardian_review.failed", target=row.review_id, details={"provider": row.provider, "model": row.model_requested, "schema_version": row.schema_version, "prompt_version": row.prompt_version, "attempts": row.attempts, "error_code": code, "status": row.status})
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
