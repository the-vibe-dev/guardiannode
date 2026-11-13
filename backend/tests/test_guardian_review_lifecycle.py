"""Provider completion must respect deletion and consent changes in flight."""
from __future__ import annotations

import pytest

from app.db.models import AuditLog, Event, GuardianReview, GuardianReviewPreview
from app.db.session import get_sessionmaker
from app.services import guardian_review, purge
from app.services.guardian_review_providers import ProviderError, ProviderResult
from tests.test_consent_enforcement import _grant
from tests.test_guardian_review import _client, _preview, _submit, _valid_assessment


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "retryable_error", "terminal_error"])
async def test_worker_discards_outcome_after_incident_is_deleted(monkeypatch, tmp_path, outcome):
    client = _client(monkeypatch, tmp_path)
    accepted = _submit(client, _preview(client))

    class DeleteWhileProcessing:
        calls = 0

        async def assess(self, **_kwargs):
            self.calls += 1
            with get_sessionmaker()() as other:
                assert purge.delete_events(other, ["event-1"])["events"] == 1
                other.commit()
            if outcome != "success":
                raise ProviderError("upstream_timeout", retryable=outcome == "retryable_error")
            return ProviderResult(_valid_assessment(), "synthetic-model", "synthetic-response", 1)

    provider = DeleteWhileProcessing()

    async def no_retry(_delay):
        pytest.fail("A deleted incident must not be retried")

    with get_sessionmaker()() as db:
        assert await guardian_review.process_one(db, provider_override=provider, sleep=no_retry)
        assert provider.calls == 1
        assert db.get(GuardianReview, accepted["review_id"]) is None
        assert db.query(GuardianReviewPreview).count() == 0
        assert db.get(Event, "event-1") is None
        assert db.query(AuditLog).filter(
            AuditLog.action.in_(["guardian_review.completed", "guardian_review.failed"])
        ).count() == 0


@pytest.mark.asyncio
async def test_worker_discards_external_result_after_consent_changes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client, external_ai=True)
    accepted = _submit(client, _preview(client))
    # The injected provider is synthetic; only the row's delivery policy is external.
    with get_sessionmaker()() as db:
        row = db.get(GuardianReview, accepted["review_id"])
        row.provider = "openai"
        db.commit()

    class RevokeWhileProcessing:
        async def assess(self, **_kwargs):
            _grant(client, external_ai=False)
            return ProviderResult(_valid_assessment(), "synthetic-model", "synthetic-response", 1)

    with get_sessionmaker()() as db:
        assert await guardian_review.process_one(db, provider_override=RevokeWhileProcessing())
        row = db.get(GuardianReview, accepted["review_id"])
        assert row.status == "failed"
        assert row.error_code == "external_ai_consent_required"
        assert row.assessment_enc is None
        assert row.provider_response_id is None
        assert db.query(AuditLog).filter(AuditLog.action == "guardian_review.completed").count() == 0
