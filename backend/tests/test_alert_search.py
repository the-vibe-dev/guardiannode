"""Complete-history alert browsing, literal search, and UTC range contracts."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import Alert, ChildProfile, Device, Event, RiskResult
from app.db.session import get_sessionmaker
from tests.test_readiness_apis import _client


@pytest.fixture
def feed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    with get_sessionmaker()() as db:
        db.add_all([
            ChildProfile(profile_id="child-a", display_name="Alex", age_group="10_13"),
            ChildProfile(profile_id="child-b", display_name="Sam", age_group="14_17"),
        ])
        db.flush()
        db.add_all([
            Device(device_id="pc-a", hostname="pc-a", paired=True, profile_id="child-a"),
            Device(device_id="pc-b", hostname="pc-b", paired=True, profile_id="child-b"),
        ])
        db.flush()
        for index in range(65):
            device = "pc-a" if index % 2 == 0 else "pc-b"
            profile = "child-a" if index % 2 == 0 else "child-b"
            # Many alerts deliberately share timestamps: cursors need a stable tie break.
            created = now if index > 0 else now - timedelta(days=1)
            db.add(Event(
                event_id=f"event-{index:03}", device_id=device, profile_id=profile,
                source_type="system", app_name="SpecialGame.exe" if index == 1 else "chat.exe",
                timestamp=created,
            ))
            db.flush()
            db.add(RiskResult(
                risk_id=f"risk-{index:03}", event_id=f"event-{index:03}",
                risk_level="high", score=75,
                categories=["grooming"] if index == 2 else ["bullying"],
                summary="Literal 100%_match old incident" if index == 0 else "Ordinary incident",
            ))
            db.flush()
            db.add(Alert(
                alert_id=f"alert-{index:03}", risk_id=f"risk-{index:03}",
                device_id=device, profile_id=profile, severity="high", status="open",
                created_at=created,
            ))
        db.commit()
    return client


def test_search_reaches_alert_beyond_default_first_page(feed):
    first = feed.get("/api/alerts").json()
    assert len(first["items"]) == 50
    assert "alert-000" not in {item["alert_id"] for item in first["items"]}
    result = feed.get("/api/alerts", params={"q": "OLD INCIDENT"})
    assert result.status_code == 200
    assert [item["alert_id"] for item in result.json()["items"]] == ["alert-000"]
    assert result.json()["open_count"] == 65


@pytest.mark.parametrize(("query", "expected"), [
    ("SpecialGame.exe", "alert-001"),
    ("grooming", "alert-002"),
    ("100%_match", "alert-000"),
    ("%", "alert-000"),
])
def test_searches_metadata_and_treats_sql_wildcards_literally(feed, query, expected):
    result = feed.get("/api/alerts", params={"q": query})
    assert result.status_code == 200
    assert [item["alert_id"] for item in result.json()["items"]] == [expected]


def test_cursor_exhausts_same_timestamp_results_without_gaps_or_duplicates(feed):
    ids = []
    cursor = None
    for _ in range(10):
        params = {"limit": 7, "device_id": "pc-a", "profile_id": "child-a", "q": "incident"}
        if cursor:
            params["cursor"] = cursor
        response = feed.get("/api/alerts", params=params)
        assert response.status_code == 200
        page = response.json()
        ids.extend(item["alert_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert ids == [f"alert-{index:03}" for index in range(64, -1, -2)]


def test_time_range_is_inclusive_start_exclusive_end_with_offsets(feed):
    result = feed.get("/api/alerts", params={
        "since": "2026-11-09T07:00:00-05:00",
        "until": "2026-11-10T12:00:00Z",
    })
    assert result.status_code == 200
    assert [item["alert_id"] for item in result.json()["items"]] == ["alert-000"]


@pytest.mark.parametrize("params", [
    {"since": "2026-11-09T12:00:00"},
    {"until": "2026-11-10T12:00:00"},
    {"since": "2026-11-10T12:00:00Z", "until": "2026-11-09T12:00:00Z"},
    {"since": "2026-11-10T12:00:00Z", "until": "2026-11-10T12:00:00Z"},
    {"q": "x" * 201},
])
def test_rejects_ambiguous_or_unbounded_filter_input(feed, params):
    assert feed.get("/api/alerts", params=params).status_code == 422


def test_invalid_cursor_is_reported(feed):
    assert feed.get("/api/alerts", params={"cursor": "missing"}).status_code == 400


def test_alert_search_requires_parent_session(feed):
    feed.cookies.clear()
    assert feed.get("/api/alerts", params={"q": "incident"}).status_code == 401
