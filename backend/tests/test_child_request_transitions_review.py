"""Retired exception workflows preserve historical records without decisions."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import ChildRequest
from app.db.session import get_sessionmaker
from tests.test_readiness_apis import _client


def _request(*, request_id="request-1", status="open", expired=False):
    with get_sessionmaker()() as db:
        row = ChildRequest(
            request_id=request_id, request_type="more_time", status=status,
            expires_at=datetime.now(UTC) + timedelta(days=-1 if expired else 1),
        )
        db.add(row)
        db.commit()


def test_parent_cannot_overwrite_an_existing_decision(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _request(status="approved")
    first = client.post("/api/child-requests/request-1/review", json={
        "status": "approved", "response_note": "After homework.",
    })
    assert first.status_code == 410
    stale = client.post("/api/child-requests/request-1/review", json={
        "status": "denied", "response_note": "stale response",
    })
    assert stale.status_code == 410
    stored = client.get("/api/child-requests").json()["items"][0]
    assert stored["status"] == "approved"
    assert stored["response_note"] is None


def test_expired_request_cannot_be_reviewed_even_without_prior_list(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _request(expired=True)
    response = client.post("/api/child-requests/request-1/review", json={"status": "approved"})
    assert response.status_code == 410
    with get_sessionmaker()() as db:
        assert db.get(ChildRequest, "request-1").status == "open"


def test_list_expiration_applies_before_open_filter_and_count(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _request(request_id="old", expired=True)
    _request(request_id="current")
    body = client.get("/api/child-requests", params={"status": "open"}).json()
    assert body["open_count"] == 1
    assert [item["request_id"] for item in body["items"]] == ["current"]


def test_missing_request_review_is_also_retired(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/child-requests/missing/review", json={"status": "approved"})
    assert response.status_code == 410
