"""Parent-authorized Guardian Review routes."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.api.deps import get_db_dep, parent_user, require_critical_auth, require_recent_auth
from app.db.models import User
from app.guardian_review_models import (
    GuardianReviewContext,
    ReviewAccepted,
    ReviewPreviewResponse,
    ReviewResult,
    ReviewSubmitRequest,
)
from app.services import guardian_review as workflow
from app.services import guardian_review_codex_auth as codex_auth
from app.services.audit import log_action

router = APIRouter(tags=["guardian-review"])


def _error(exc: workflow.WorkflowError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": workflow._error_message(exc.code), "retryable": False, "review_id": None}},
    )


@router.get("/guardian-review/providers")
def providers(user: User = Depends(parent_user)) -> dict:
    settings = settings_mod.settings
    codex = codex_auth.status(executable=settings.codex_executable, codex_home=settings.codex_home_resolved)
    return {
        "enabled": settings.guardian_review_enabled,
        "selected": settings.guardian_review_provider,
        "model": workflow.configured_model(settings.guardian_review_provider),
        "providers": {
            "mock": {"available": settings.dev_mode or settings.guardian_review_provider == "mock"},
            "codex": {"available": codex["installed"], **codex},
            "openai": {"available": bool((settings.openai_api_key or os.getenv("OPENAI_API_KEY")) and settings.guardian_review_zdr_confirmed), "api_key_configured": bool(settings.openai_api_key or os.getenv("OPENAI_API_KEY")), "zdr_confirmed": settings.guardian_review_zdr_confirmed},
        },
        "actor": str(user.id),
    }


@router.post("/guardian-review/providers/codex/device-login")
def start_codex_login(
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
    _: None = Depends(require_critical_auth),
) -> dict:
    settings = settings_mod.settings
    result = codex_auth.start(executable=settings.codex_executable, codex_home=settings.codex_home_resolved)
    log_action(db, actor=str(user.id), action="guardian_review.provider_connect_started", target="codex", details={"status": result["status"]})
    db.commit()
    return result


@router.get("/guardian-review/providers/codex/device-login/{session_id}")
def codex_login_status(session_id: str, _: User = Depends(parent_user)):
    result = codex_auth.get(session_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Connection session not found.", "retryable": False, "review_id": None}})
    return result


@router.delete("/guardian-review/providers/codex/device-login/{session_id}")
def cancel_codex_login(
    session_id: str,
    _: User = Depends(parent_user),
    __: None = Depends(require_critical_auth),
):
    if not codex_auth.cancel(session_id):
        return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Connection session not found.", "retryable": False, "review_id": None}})
    return {"status": "cancelled"}


@router.post("/alerts/{alert_id}/guardian-review/preview", response_model=ReviewPreviewResponse)
def preview(
    alert_id: str,
    request: GuardianReviewContext,
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
):
    try:
        return workflow.create_preview(db, alert_id=alert_id, context=request, user=user)
    except workflow.WorkflowError as exc:
        return _error(exc)


@router.post("/alerts/{alert_id}/guardian-review", response_model=ReviewAccepted, status_code=202)
def submit(
    alert_id: str,
    request: ReviewSubmitRequest,
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
    _: None = Depends(require_recent_auth),
):
    try:
        return workflow.submit_review(db, alert_id=alert_id, preview_id=request.preview_id, preview_digest=request.preview_digest, user=user)
    except workflow.WorkflowError as exc:
        return _error(exc)


@router.get("/guardian-reviews/{review_id}", response_model=ReviewResult)
def result(
    review_id: str,
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
):
    try:
        return workflow.get_result(db, review_id=review_id, user=user)
    except workflow.WorkflowError as exc:
        return _error(exc)
