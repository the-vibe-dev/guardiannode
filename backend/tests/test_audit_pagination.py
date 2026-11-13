"""Parent audit browsing must cover retained history without unstable offsets."""
from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import AuditLog, User
from app.db.session import get_sessionmaker
from tests.test_readiness_apis import _client


@pytest.fixture
def audit_feed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = datetime(2026, 11, 10, 12, tzinfo=UTC)
    with get_sessionmaker()() as db:
        rows = [AuditLog(
            actor="parent-a" if index % 2 == 0 else "parent-b",
            action="synthetic.review",
            target="Historical 100%_match" if index == 0 else f"entry-{index}",
            source_ip="192.0.2.1" if index == 1 else None,
            details={"private": "evidence-only-marker"},
            created_at=created if index else created - timedelta(days=1),
        ) for index in range(260)]
        db.add_all(rows)
        db.commit()
        ids = [row.id for row in rows]
    return client, ids


def test_all_retained_rows_can_be_paged_with_same_timestamp_ties(audit_feed):
    client, ids = audit_feed
    cursor = None
    found = []
    for _ in range(10):
        params = {"action": "synthetic.review", "limit": 37}
        if cursor:
            params["cursor"] = cursor
        result = client.get("/api/audit/page", params=params)
        assert result.status_code == 200
        page = result.json()
        assert page["total"] == 260
        found.extend(row["id"] for row in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert found == list(reversed(ids))
    assert len(set(found)) == 260


@pytest.mark.parametrize("query,offset", [
    ("HISTORICAL", 0), ("100%_match", 0), ("%", 0), ("192.0.2.1", 1),
])
def test_metadata_search_reaches_old_rows_and_escapes_wildcards(audit_feed, query, offset):
    client, ids = audit_feed
    page = client.get("/api/audit/page", params={"q": query}).json()
    assert [row["id"] for row in page["items"]] == [ids[offset]]
    assert page["total"] == 1


def test_search_does_not_query_private_details_and_exact_filters_combine(audit_feed):
    client, ids = audit_feed
    assert client.get("/api/audit/page", params={"q": "evidence-only-marker"}).json()["total"] == 0
    response = client.get("/api/audit/page", params={
        "action": "synthetic.review", "actor": "parent-a", "q": "historical",
    })
    assert [row["id"] for row in response.json()["items"]] == [ids[0]]
    assert client.get("/api/audit/page", params={"actor": "parent"}).json()["total"] == 0


def test_utc_range_is_inclusive_start_exclusive_end(audit_feed):
    client, ids = audit_feed
    response = client.get("/api/audit/page", params={
        "since": "2026-11-09T07:00:00-05:00", "until": "2026-11-10T12:00:00Z",
    })
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [ids[0]]
    assert response.json()["items"][0]["created_at"].endswith("Z")


@pytest.mark.parametrize("params", [
    {"since": "2026-11-09T12:00:00"},
    {"until": "2026-11-10T12:00:00"},
    {"since": "2026-11-10T12:00:00Z", "until": "2026-11-10T12:00:00Z"},
    {"since": "2026-11-11T12:00:00Z", "until": "2026-11-10T12:00:00Z"},
    {"limit": 101}, {"q": "x" * 201},
])
def test_invalid_or_unbounded_filters_are_rejected(audit_feed, params):
    client, _ = audit_feed
    assert client.get("/api/audit/page", params=params).status_code == 422


def test_cursor_binds_filters_and_rejects_invalid_payloads(audit_feed):
    client, _ = audit_feed
    page = client.get("/api/audit/page", params={"actor": "parent-a", "limit": 2}).json()
    token = page["next_cursor"]
    assert client.get("/api/audit/page", params={"cursor": token}).status_code == 400
    assert client.get("/api/audit/page", params={"cursor": "!invalid"}).status_code == 400
    payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    for field, value in (("id", True), ("id", 2**64), ("time", "2026-11-10T12:00:00"), ("v", 2)):
        broken = base64.urlsafe_b64encode(json.dumps({**payload, field: value}).encode()).decode()
        assert client.get("/api/audit/page", params={
            "actor": "parent-a", "cursor": broken,
        }).status_code == 400


def test_deleted_anchor_and_newer_entries_do_not_duplicate_or_lose_history(audit_feed):
    client, ids = audit_feed
    first = client.get("/api/audit/page", params={"action": "synthetic.review", "limit": 2}).json()
    assert [row["id"] for row in first["items"]] == list(reversed(ids[-2:]))
    with get_sessionmaker()() as db:
        db.delete(db.get(AuditLog, ids[-2]))
        db.add(AuditLog(actor="parent-a", action="synthetic.review", created_at=datetime.now(UTC)))
        db.commit()
    following = client.get("/api/audit/page", params={
        "action": "synthetic.review", "limit": 2, "cursor": first["next_cursor"],
    })
    assert following.status_code == 200
    assert [row["id"] for row in following.json()["items"]] == [ids[-3], ids[-4]]


def test_parent_auth_required_and_legacy_list_remains_compatible(audit_feed):
    client, _ = audit_feed
    assert isinstance(client.get("/api/audit", params={"limit": 3}).json(), list)
    with get_sessionmaker()() as db:
        db.query(User).first().role = "viewer"
        db.commit()
    assert client.get("/api/audit/page").status_code == 403
    assert client.get("/api/audit").status_code == 403
    client.cookies.clear()
    assert client.get("/api/audit/page").status_code == 401
