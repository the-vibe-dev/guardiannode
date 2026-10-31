"""Parent choices must hold at enqueue and worker side-effect boundaries."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, Request

from app import settings as settings_mod
from app.api.consent import ConsentWithdrawalRequest, withdraw_consent
from app.api.deps import current_device
from app.api.devices import HeartbeatRequest, heartbeat
from app.db.models import Alert, ConsentRecord, Device, Event, RiskResult, User
from app.guardian_review_models import GuardianReviewContext
from app.services import consent, device_tokens, encryption, guardian_review
from app.services.guardian_review_providers import ProviderError


def _incident(db):
    user = User(display_name="Synthetic Parent", password_hash="synthetic", recovery_hash="synthetic")
    db.add(user)
    db.add(Device(device_id="synthetic-device", hostname="synthetic", paired=True))
    db.flush()
    db.add(Event(
        event_id="synthetic-event", device_id="synthetic-device", source_type="image",
        timestamp=datetime.now(UTC),
        redacted_text_enc=encryption.encrypt_text("Synthetic secrecy request"),
    ))
    db.add(RiskResult(
        risk_id="synthetic-risk", event_id="synthetic-event", risk_level="high",
        score=70, summary="Synthetic secrecy request", evidence=["Synthetic secrecy request"],
        categories=["secrecy_request"],
    ))
    db.flush()
    db.add(Alert(
        alert_id="synthetic-alert", risk_id="synthetic-risk", device_id="synthetic-device",
        severity="high",
    ))
    db.commit()
    return user


def _consent(db, user, *, consent_id="generation-1", status="granted", **changes):
    choices = {
        "screenshots": True, "apps_and_urls": True, "retention": True,
        "notifications": True, "external_ai": False,
        "child_notice_acknowledged": True,
    }
    choices.update(changes)
    db.add(ConsentRecord(
        consent_id=consent_id, user_id=user.id, notice_version=consent.NOTICE_VERSION,
        status=status, choices=choices,
        created_at=datetime.now(UTC) + (timedelta(seconds=1) if status == "withdrawn" else timedelta()),
    ))
    db.commit()


def test_all_capture_choices_off_disable_monitoring(db_session):
    user = _incident(db_session)
    _consent(db_session, user, screenshots=False, apps_and_urls=False, retention=False,
             notifications=False, external_ai=False)
    assert consent.monitoring_allowed(db_session) is False
    assert consent.effective_policy(db_session).apps_and_urls is False


def test_external_review_requires_global_opt_in(db_session, monkeypatch):
    user = _incident(db_session)
    _consent(db_session, user)
    monkeypatch.setattr(settings_mod.settings, "guardian_review_enabled", True)
    monkeypatch.setattr(settings_mod.settings, "guardian_review_provider", "openai")
    monkeypatch.setattr(settings_mod.settings, "guardian_review_zdr_confirmed", True)
    monkeypatch.setattr(settings_mod.settings, "openai_api_key", "synthetic-test-key")
    with pytest.raises(guardian_review.WorkflowError) as exc:
        guardian_review.create_preview(
            db_session, alert_id="synthetic-alert", context=GuardianReviewContext(), user=user,
        )
    assert exc.value.code == "external_ai_not_allowed"


def test_withdrawal_fences_queued_review_before_provider(db_session, monkeypatch):
    user = _incident(db_session)
    _consent(db_session, user, external_ai=True)
    monkeypatch.setattr(settings_mod.settings, "guardian_review_enabled", True)
    monkeypatch.setattr(settings_mod.settings, "guardian_review_provider", "mock")
    preview = guardian_review.create_preview(
        db_session, alert_id="synthetic-alert", context=GuardianReviewContext(), user=user,
    )
    guardian_review.submit_review(
        db_session, alert_id="synthetic-alert", preview_id=preview.preview_id,
        preview_digest=preview.preview_digest, user=user,
    )
    _consent(db_session, user, consent_id="withdrawn", status="withdrawn")
    calls = []

    class Spy:
        async def assess(self, **kwargs):
            calls.append(kwargs)
            raise ProviderError("upstream_unavailable")

    asyncio.run(guardian_review.process_one(db_session, provider_override=Spy()))
    assert calls == []


def test_stale_running_review_with_dispatched_attempt_is_not_retried(db_session):
    from app.db.models import GuardianReview, GuardianReviewPreview

    user = _incident(db_session)
    db_session.add(GuardianReviewPreview(
        preview_id="p", alert_id="synthetic-alert", actor_user_id=user.id,
        provider="mock", model_requested="mock", schema_version="1.1.0",
        prompt_version="guardian-review-v2", payload_digest="0" * 64,
        incident_fingerprint="1" * 64, expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    db_session.flush()
    db_session.add(GuardianReview(
        review_id="r", preview_id="p", alert_id="synthetic-alert",
        requester_user_id=user.id, provider="mock", dedup_key="2" * 64,
        schema_version="1.1.0", prompt_version="guardian-review-v2",
        model_requested="mock", status="running", attempts=1,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
    ))
    db_session.commit()
    assert guardian_review.recover_stale_jobs(db_session) == 1
    assert db_session.get(GuardianReview, "r").error_code == "outcome_uncertain"


def _request(path: str, token: str = "") -> Request:
    return Request({
        "type": "http", "method": "POST", "path": path,
        "headers": [(b"authorization", f"Bearer {token}".encode())] if token else [],
        "client": ("127.0.0.1", 1234), "scheme": "http", "server": ("testserver", 80),
    })


def test_withdrawal_token_is_control_only_until_broker_ack(db_session):
    user = _incident(db_session)
    _consent(db_session, user)
    token, digest = device_tokens.issue_token("synthetic-device")
    device = db_session.get(Device, "synthetic-device")
    device.token_hash = digest
    db_session.commit()

    result = withdraw_consent(
        ConsentWithdrawalRequest(evidence_disposition="retain"),
        _request("/api/consent/withdraw"), db_session, user, None,
    )
    generation = result["record"]["consent_id"]
    assert device.status == "consent_stop_requested"
    assert device.paired is True
    with pytest.raises(HTTPException) as denied:
        current_device(_request("/api/events/screenshot", token), db_session)
    assert denied.value.status_code == 403
    control_device = current_device(_request("/api/devices/capture-config", token), db_session)
    assert control_device.device_id == device.device_id

    heartbeat(HeartbeatRequest(applied_policy_generation="stale-generation"), db_session, device)
    assert device.status == "consent_stop_requested"
    heartbeat(HeartbeatRequest(applied_policy_generation=generation), db_session, device)
    assert device.status == "consent_stop_applied"
    assert device.token_hash is None
    with pytest.raises(HTTPException) as stale:
        current_device(_request("/api/devices/capture-config", token), db_session)
    assert stale.value.status_code == 401


def test_withdrawal_marks_unpaired_device_offline(db_session):
    user = _incident(db_session)
    _consent(db_session, user)
    result = withdraw_consent(
        ConsentWithdrawalRequest(evidence_disposition="retain"),
        _request("/api/consent/withdraw"), db_session, user, None,
    )
    assert result["active"] is False
    assert db_session.get(Device, "synthetic-device").status == "consent_stop_offline"
