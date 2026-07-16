from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db.models import (
    Alert,
    ChildProfile,
    Device,
    Event,
    GuardianReview,
    GuardianReviewPreview,
    RiskResult,
    User,
)
from app.guardian_review_models import (
    GuardianReviewAssessment,
    strict_output_schema,
)
from app.services import encryption, guardian_review
from app.services.guardian_review_minimization import minimize_text
from app.services.guardian_review_providers import (
    CodexProvider,
    OpenAIResponsesProvider,
    ProviderError,
    ProviderResult,
)


def _client(monkeypatch, tmp_path: Path, *, provider: str = "mock") -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings(
        guardian_review_enabled=True,
        guardian_review_provider=provider,
        guardian_review_zdr_confirmed=provider == "openai",
        mdns_enabled=False,
        retention_cleanup_enabled=False,
        device_offline_alert_enabled=False,
        notification_worker_enabled=False,
        database_backup_enabled=False,
    )
    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app
    from app.services.setup_token import ensure_setup_token

    Base.metadata.create_all(bind=get_engine())
    client = TestClient(create_app())
    response = client.post(
        "/api/auth/setup",
        json={
            "display_name": "Parent",
            "password": "correct horse battery",
            "recovery_code": "one two three",
            "setup_token": ensure_setup_token(),
        },
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]})
    _seed_incident()
    return client


def _seed_incident() -> None:
    from app.db.session import get_sessionmaker

    db = get_sessionmaker()()
    try:
        db.add(ChildProfile(profile_id="profile-1", display_name="Avery", age_group="10_13", custom_watch_phrases=["Example Middle School"]))
        db.add(Device(device_id="device-1", hostname="family-pc", platform="windows", paired=True, profile_id="profile-1"))
        text = "Avery contact me at child@example.test or https://private.test near 123 Main Street Example Middle School"
        db.add(Event(event_id="event-1", device_id="device-1", profile_id="profile-1", source_type="image", app_name="private.exe", window_title="private", url="https://never-send.test", timestamp=datetime.now(UTC), redacted_text_enc=encryption.encrypt_text(text)))
        db.add(RiskResult(risk_id="risk-1", event_id="event-1", risk_level="high", score=82, categories=["grooming"], summary=text, evidence=[text], recommended_action="parent_review", rules_triggered=["secrecy_request"], confidence=0.8, classifier_status="ok"))
        db.flush()
        db.add(Alert(alert_id="alert-1", risk_id="risk-1", device_id="device-1", profile_id="profile-1", severity="high", repeat_count=2))
        db.commit()
    finally:
        db.close()


def _preview(client: TestClient, *, fresh: bool = False) -> dict:
    response = client.post(
        "/api/alerts/alert-1/guardian-review/preview",
        json={
            "relationship_context": "unknown_person",
            "repeated_behavior": "yes",
            "parent_believes_immediate_danger": False,
            "parent_goal": "prepare_conversation",
            "parent_context": "Contact parent@example.test, not the child.",
            "fresh_assessment": fresh,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _submit(client: TestClient, preview: dict) -> dict:
    response = client.post(
        "/api/alerts/alert-1/guardian-review",
        json={"preview_id": preview["preview_id"], "preview_digest": preview["preview_digest"], "consent": True},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _walk_objects(schema: dict):
    if schema.get("type") == "object":
        yield schema
    for value in schema.values():
        if isinstance(value, dict):
            yield from _walk_objects(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _walk_objects(item)


def test_strict_schema_closes_every_object_and_rejects_extra_fields():
    schema = strict_output_schema()
    assert schema["properties"]["schema_version"]["const"] == "1.1.0"
    assert {"observed_facts", "inferences"}.issubset(schema["required"])
    assert all(obj.get("additionalProperties") is False for obj in _walk_objects(schema))
    with pytest.raises(ValidationError):
        GuardianReviewAssessment.model_validate({"schema_version": "1.1.0", "unexpected": True})


def test_prompt_contract_contains_required_safety_boundaries():
    prompt = (Path(__file__).parents[1] / "app" / "prompts" / "guardian_review_v1.txt").read_text("utf-8").lower()
    for phrase in (
        "observed facts",
        "definitive accusations",
        "benign explanations",
        "medical, psychological, or legal",
        "imminent danger",
        "parent as final decision-maker",
        "untrusted quoted data",
    ):
        assert phrase in prompt


def test_preview_loads_server_incident_and_redacts_sensitive_fields(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    preview = _preview(client)
    outbound = json.dumps(preview["outbound_payload"])
    assert "Avery" not in outbound
    assert "example.test" not in outbound
    assert "Example Middle School" not in outbound
    assert "123 Main Street" not in outbound
    assert "private.exe" not in outbound
    assert "never-send" not in outbound
    assert {"address", "email", "profile_term", "url"}.issubset(preview["redactions_applied"])
    assert preview["outbound_payload"]["approximate_child_age_group"] == "10_13"


def test_preview_rejects_unbounded_or_invalid_evidence_ids(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/alerts/alert-1/guardian-review/preview",
        json={"selected_evidence_ids": ["x" * 129]},
    )
    assert response.status_code == 422


def test_complete_mock_route_persists_encrypted_result_and_deduplicates(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    preview = _preview(client)
    accepted = _submit(client, preview)
    assert _submit(client, preview)["review_id"] == accepted["review_id"]
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        asyncio.run(guardian_review.process_one(db))
        row = db.get(GuardianReview, accepted["review_id"])
        assert row is not None and row.assessment_enc
        assert b"plain_language_summary" not in row.assessment_enc
        assert db.query(GuardianReview).count() == 1
    finally:
        db.close()
    result = client.get(accepted["status_url"])
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["assessment"]["schema_version"] == "1.1.0"


def test_fresh_assessment_creates_new_review(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    first = _submit(client, _preview(client))
    duplicate = _submit(client, _preview(client))
    fresh = _submit(client, _preview(client, fresh=True))
    assert duplicate["review_id"] == first["review_id"]
    assert fresh["review_id"] != first["review_id"]


def test_invalid_incident_tampered_digest_and_viewer_are_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    missing = client.post("/api/alerts/missing/guardian-review/preview", json={})
    assert missing.status_code == 404
    preview = _preview(client)
    stale = client.post(
        "/api/alerts/alert-1/guardian-review",
        json={"preview_id": preview["preview_id"], "preview_digest": "0" * 64, "consent": True},
    )
    assert stale.status_code == 409
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        db.query(User).filter(User.display_name == "Parent").one().role = "viewer"
        db.commit()
    finally:
        db.close()
    assert client.get("/api/guardian-review/providers").status_code == 403


def test_unauthenticated_preview_is_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    client.headers.pop("X-CSRF-Token")
    client.post("/api/auth/logout", headers={"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]})
    assert client.post("/api/alerts/alert-1/guardian-review/preview", json={}).status_code == 401


def _valid_assessment() -> GuardianReviewAssessment:
    from app.services.guardian_review_providers import _mock_assessment
    return _mock_assessment({"local_detector_findings": {"severity": "medium", "categories": ["unknown"]}, "minimized_evidence": []})


@pytest.mark.asyncio
async def test_responses_api_uses_store_false_and_strict_schema():
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "resp_1", "model": "gpt-5.6-2026-07-01", "output": [{"content": [{"type": "output_text", "text": _valid_assessment().model_dump_json()}]}]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await OpenAIResponsesProvider(api_key="test-only", base_url="https://api.openai.test/v1", client=client).assess(payload={"incident_id": "synthetic"}, prompt="contract", model="gpt-5.6", timeout=1)
    finally:
        await client.aclose()
    assert seen["store"] is False
    assert seen["model"] == "gpt-5.6"
    assert seen["tools"] == []
    assert seen["text"]["format"]["strict"] is True
    assert result.model_returned == "gpt-5.6-2026-07-01"


@pytest.mark.asyncio
async def test_responses_api_rejects_malformed_output_and_missing_key():
    with pytest.raises(ProviderError, match="provider_auth_required"):
        await OpenAIResponsesProvider(api_key=None, base_url="https://api.openai.test/v1").assess(payload={}, prompt="x", model="gpt-5.6", timeout=0.01)
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"output_text": "{}"})))
    try:
        with pytest.raises(ProviderError, match="invalid_model_output") as exc:
            await OpenAIResponsesProvider(api_key="test", base_url="https://api.openai.test/v1", client=client).assess(payload={}, prompt="x", model="gpt-5.6", timeout=1)
        assert exc.value.retryable is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_responses_timeout_is_retryable_and_policy_error_is_not():
    timeout_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request))
        )
    )
    try:
        with pytest.raises(ProviderError, match="upstream_timeout") as timeout_error:
            await OpenAIResponsesProvider(api_key="test", base_url="https://api.openai.test/v1", client=timeout_client).assess(payload={}, prompt="x", model="gpt-5.6", timeout=1)
        assert timeout_error.value.retryable is True
    finally:
        await timeout_client.aclose()
    policy_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
        )
    )
    try:
        with pytest.raises(ProviderError, match="upstream_policy_or_validation") as policy_error:
            await OpenAIResponsesProvider(api_key="test", base_url="https://api.openai.test/v1", client=policy_client).assess(payload={}, prompt="x", model="gpt-5.6", timeout=1)
        assert policy_error.value.retryable is False
    finally:
        await policy_client.aclose()


@pytest.mark.asyncio
async def test_missing_codex_executable_is_safely_unavailable(tmp_path):
    provider = CodexProvider(executable=str(tmp_path / "missing-codex"), codex_home=tmp_path / "home")
    with pytest.raises(ProviderError, match="provider_unavailable") as exc:
        await provider.assess(payload={}, prompt="x", model="gpt-5.6", timeout=1)
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_codex_policy_error_is_not_retried_or_exposed(tmp_path):
    executable = tmp_path / "codex-test"
    executable.write_text("#!/bin/sh\necho 'invalid_request_error: model not supported' >&2\nexit 1\n", encoding="utf-8")
    executable.chmod(0o700)
    provider = CodexProvider(executable=str(executable), codex_home=tmp_path / "home")
    with pytest.raises(ProviderError, match="upstream_policy_or_validation") as exc:
        await provider.assess(payload={"synthetic": True}, prompt="x", model="gpt-5.6", timeout=1)
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_codex_timeout_terminates_process_group(tmp_path):
    executable = tmp_path / "codex-slow"
    executable.write_text("#!/bin/sh\nsleep 10\n", encoding="utf-8")
    executable.chmod(0o700)
    provider = CodexProvider(executable=str(executable), codex_home=tmp_path / "home")
    with pytest.raises(ProviderError, match="upstream_timeout") as exc:
        await provider.assess(payload={"synthetic": True}, prompt="x", model="gpt-5.6-sol", timeout=0.05)
    assert exc.value.retryable is True


class _SequenceProvider:
    def __init__(self, errors: list[ProviderError]):
        self.errors = errors
        self.calls = 0

    async def assess(self, **_kwargs) -> ProviderResult:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return ProviderResult(_valid_assessment(), "gpt-5.6-test", "resp-test", 12)


@pytest.mark.asyncio
async def test_worker_retries_only_transient_failures(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    accepted = _submit(client, _preview(client))
    sleeps = []
    async def fake_sleep(value):
        sleeps.append(value)
    provider = _SequenceProvider([ProviderError("upstream_timeout", retryable=True, retry_after=0)])
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        await guardian_review.process_one(db, provider_override=provider, sleep=fake_sleep)
        row = db.get(GuardianReview, accepted["review_id"])
        assert row.status == "completed" and row.attempts == 2
        assert sleeps == [0]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_worker_does_not_retry_validation_or_policy_failure(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    accepted = _submit(client, _preview(client))
    provider = _SequenceProvider([ProviderError("invalid_model_output", retryable=False)])
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        await guardian_review.process_one(db, provider_override=provider)
        row = db.get(GuardianReview, accepted["review_id"])
        assert row.status == "failed" and row.attempts == 1
        assert row.error_code == "invalid_model_output"
    finally:
        db.close()


def test_missing_openai_key_disables_live_preview_without_exposing_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _client(monkeypatch, tmp_path, provider="openai")
    response = client.post("/api/alerts/alert-1/guardian-review/preview", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_auth_required"
    assert "key" not in json.dumps(response.json()).lower()
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        assert db.query(GuardianReview).count() == 0
    finally:
        db.close()


def test_changed_incident_invalidates_preview(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    preview = _preview(client)
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        db.get(Alert, "alert-1").repeat_count = 3
        db.commit()
    finally:
        db.close()
    response = client.post(
        "/api/alerts/alert-1/guardian-review",
        json={"preview_id": preview["preview_id"], "preview_digest": preview["preview_digest"], "consent": True},
    )
    assert response.status_code == 409


def test_audit_log_never_contains_raw_context(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    accepted = _submit(client, _preview(client))
    from app.db.models import AuditLog
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        asyncio.run(guardian_review.process_one(db))
        audit_json = json.dumps([row.details for row in db.query(AuditLog).all()])
        assert "parent@example.test" not in audit_json
        assert "Avery" not in audit_json
        assert accepted["review_id"] in {row.target for row in db.query(AuditLog).all()}
    finally:
        db.close()


def test_preview_rows_are_encrypted(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    preview = _preview(client)
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        row = db.get(GuardianReviewPreview, preview["preview_id"])
        assert row is not None
        assert b"parent@example.test" not in row.payload_enc
    finally:
        db.close()


def test_synthetic_harness_mock_mode_needs_no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.guardian_review_harness import _run

    result = asyncio.run(
        _run(
            argparse.Namespace(
                provider="mock",
                scenario="ambiguous-joke",
                data_dir=tmp_path / "harness",
                codex_home=tmp_path / "codex",
                confirm_live=False,
                fresh=False,
            )
        )
    )
    assert result["synthetic"] is True
    assert result["result"]["status"] == "completed"
    assert (tmp_path / "harness" / "guardiannode.db").exists()


@pytest.mark.parametrize(
    ("raw", "forbidden", "expected_tag"),
    [
        ("Email me at parent@example.test", "parent@example.test", "email"),
        ("Email parent [at] example [dot] test", "parent", "email"),
        ("Call +1 (212) 555-0199 tonight", "212", "phone"),
        (r"Open C:\\Users\\Avery\\family.txt", "Avery", "path"),
        ("Open /home/avery/private/family.txt", "avery/private", "path"),
        ("Account ID: 550e8400-e29b-41d4-a716-446655440000", "550e8400", "account_id"),
        ("Username: Δανάη_17", "Δανάη_17", "username"),
        ("Meet at 40.712800, -74.006000", "40.712800", "location"),
        ("Meet near 123 Main Street", "123 Main", "address"),
    ],
)
def test_privacy_redactor_masks_sensitive_formats(raw, forbidden, expected_tag):
    cleaned, counts = minimize_text(raw, profile=None, alert_id="privacy-test")
    assert forbidden.casefold() not in cleaned.casefold()
    assert counts[expected_tag] >= 1


def test_unicode_handles_and_bypass_forms_are_normalized_and_stable():
    raw = "Talk to @søren and @søren or ｐａｒｅｎｔ＠ｅｘａｍｐｌｅ．ｔｅｓｔ and pa\u200brent@example.test"
    cleaned, counts = minimize_text(raw, profile=None, alert_id="privacy-test")
    handles = re.findall(r"\[HANDLE_[A-F0-9]{8}\]", cleaned)
    assert len(handles) == 2 and handles[0] == handles[1]
    assert "example.test" not in cleaned
    assert counts["handle"] == 2
    assert counts["email"] >= 2


def test_url_minimization_preserves_only_relevant_hostname():
    hidden, _ = minimize_text(
        "Visit https://private.example/path/to/Avery?token=secret#home",
        profile=None,
        alert_id="privacy-test",
    )
    relevant, _ = minimize_text(
        "Visit https://phish.example/login?account=Avery#prompt",
        profile=None,
        alert_id="privacy-test",
        url_destination_relevant=True,
    )
    assert "private.example" not in hidden
    assert relevant == "Visit [URL_DOMAIN:phish.example]"
    assert all(part not in relevant for part in ("login", "account", "Avery", "prompt"))


def test_empty_and_large_evidence_are_bounded(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        risk = db.get(RiskResult, "risk-1")
        event = db.get(Event, "event-1")
        risk.evidence = []
        event.redacted_text_enc = None
        db.commit()
    finally:
        db.close()
    empty = _preview(client)
    assert empty["outbound_payload"]["minimized_evidence"] == []

    db = get_sessionmaker()()
    try:
        risk = db.get(RiskResult, "risk-1")
        risk.evidence = [f"relevant-{index} " + ("x" * 2000) for index in range(30)]
        db.commit()
    finally:
        db.close()
    large = _preview(client)
    evidence = large["outbound_payload"]["minimized_evidence"]
    assert len(evidence) <= 8
    assert sum(len(item["text"]) for item in evidence) <= 4800
    assert large["character_count"] <= 12_000


def test_parent_can_remove_optional_context_and_all_evidence(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/alerts/alert-1/guardian-review/preview",
        json={
            "relationship_context": "known_peer",
            "include_evidence": False,
            "include_age_group": False,
            "parent_goal_details": None,
            "parent_context": None,
        },
    )
    assert response.status_code == 200
    payload = response.json()["outbound_payload"]
    assert payload["minimized_evidence"] == []
    assert "approximate_child_age_group" not in payload
    assert "parent_goal_details" not in payload
    assert "parent_supplied_context" not in payload


def test_cancelled_preview_is_audited_and_never_queued(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    preview = _preview(client)
    response = client.delete(f"/api/guardian-review/previews/{preview['preview_id']}")
    assert response.status_code == 204
    from app.db.models import AuditLog
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        assert db.get(GuardianReviewPreview, preview["preview_id"]) is None
        assert db.query(GuardianReview).count() == 0
        audit = db.query(AuditLog).filter(AuditLog.action == "guardian_review.cancelled").one()
        assert audit.details["parent_action"] == "cancel"
        assert audit.details["redaction_version"] == "guardian-review-redaction-v2"
    finally:
        db.close()


def test_history_and_delete_scrub_sensitive_local_content(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    accepted = _submit(client, _preview(client))
    from app.db.models import AuditLog
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        asyncio.run(guardian_review.process_one(db))
    finally:
        db.close()
    history = client.get("/api/guardian-reviews", params={"alert_id": "alert-1"})
    assert history.status_code == 200
    assert history.json()[0]["review_id"] == accepted["review_id"]
    assert history.json()[0]["has_assessment"] is True
    deleted = client.delete(f"/api/guardian-reviews/{accepted['review_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    db = get_sessionmaker()()
    try:
        row = db.get(GuardianReview, accepted["review_id"])
        preview = db.get(GuardianReviewPreview, row.preview_id)
        assert row.assessment_enc is None and row.provider_response_id is None
        assert preview.payload_enc is None
        audit = db.query(AuditLog).filter(AuditLog.action == "guardian_review.deleted").one()
        assert audit.details["parent_action"] == "delete_local_assessment"
    finally:
        db.close()


def test_viewer_cannot_access_history_cancel_or_delete(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    preview = _preview(client)
    from app.db.session import get_sessionmaker
    db = get_sessionmaker()()
    try:
        db.query(User).filter(User.display_name == "Parent").one().role = "viewer"
        db.commit()
    finally:
        db.close()
    assert client.get("/api/guardian-reviews").status_code == 403
    assert client.delete(f"/api/guardian-review/previews/{preview['preview_id']}").status_code == 403
    assert client.delete("/api/guardian-reviews/missing").status_code == 403
