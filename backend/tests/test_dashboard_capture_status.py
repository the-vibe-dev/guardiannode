from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.dashboard import capture_status
from app.db.models import Device, Event, RiskResult, ScreenshotUploadReceipt
from app.services import pipeline_metrics, screenshot_async


def test_capture_status_requires_parent_authentication() -> None:
    from app import main as main_api
    from app import settings as settings_mod
    from app.db.models import Base
    from app.db.session import get_engine

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    main_api.settings = settings_mod.settings
    Base.metadata.create_all(bind=get_engine())

    response = TestClient(main_api.create_app()).get("/api/dashboard/capture-status")

    assert response.status_code == 401


def test_capture_status_separates_acceptance_from_review(
    db_session,
    monkeypatch,
) -> None:
    captured_at = datetime(2026, 9, 8, 22, 30, tzinfo=UTC)
    db_session.add(
        Device(
            device_id="dev-1",
            hostname="Windows5",
            platform="windows",
            agent_version="test",
            paired=True,
            status="online",
        )
    )
    db_session.flush()
    db_session.add(
        ScreenshotUploadReceipt(
            device_id="dev-1",
            idempotency_key="capture-1",
            upload_id="upload-1",
            status="queued",
            created_at=captured_at,
        )
    )
    db_session.commit()

    monkeypatch.setattr(screenshot_async, "pending_count", lambda: 7)
    monkeypatch.setattr(
        pipeline_metrics,
        "snapshot",
        lambda **_kwargs: {
            "in_flight_count": 1,
            "throughput": {"p50_latency_ms": 14_000, "avg_latency_ms": 16_000},
        },
    )
    monkeypatch.setattr(
        pipeline_metrics,
        "agent_queues",
        lambda: [{"device_id": "dev-1", "hostname": "Windows5", "queued_frames": 2}],
    )

    result = capture_status(db_session, None)  # type: ignore[arg-type]

    # SQLite returns naive datetimes even for DateTime(timezone=True); the API
    # and dashboard intentionally interpret those values as UTC.
    assert result.latest_capture_at == captured_at.replace(tzinfo=None)
    assert result.latest_capture_hostname == "Windows5"
    assert result.pending_review_count == 7
    assert result.reviewing_count == 1
    assert result.waiting_upload_count == 2
    assert result.estimated_wait_seconds == 98


def test_device_review_status_requires_a_persisted_result_and_exposes_degradation(db_session, monkeypatch):
    now = datetime.now(UTC)
    definitions = [
        ("ai", "ok", "vision-model", "vision_only", "ai_reviewed"),
        ("rules", "ok", "local-rules", "rules_only", "rules_only"),
        ("degraded", "unclassified_model_unavailable", None, "vision_only", "degraded"),
        ("ocr-failed", "ocr_unavailable", "vision-model", "vision_only", "degraded"),
    ]
    for index, (device_id, status, model, tier, _expected) in enumerate(definitions):
        db_session.add(Device(device_id=device_id, hostname=device_id, paired=True, status="online"))
        db_session.flush()
        db_session.add(Event(
            event_id=device_id, device_id=device_id, source_type="image", timestamp=now,
            received_at=now, event_metadata={"tier": tier},
        ))
        db_session.flush()
        db_session.add(RiskResult(
            risk_id=device_id, event_id=device_id, risk_level="none", score=0,
            model=model, classifier_status=status, created_at=now - timedelta(minutes=10 - index),
        ))
    db_session.add(Device(device_id="event-only", hostname="No result", paired=True))
    db_session.flush()
    db_session.add_all([
        Event(event_id="event-only", device_id="event-only", source_type="image", timestamp=now),
        Event(event_id="text", device_id="ai", source_type="text", timestamp=now),
    ])
    db_session.flush()
    db_session.add(RiskResult(risk_id="text", event_id="text", risk_level="none", score=0, created_at=now))
    db_session.commit()
    monkeypatch.setattr(screenshot_async, "pending_count", lambda: 2)
    monkeypatch.setattr(screenshot_async, "pending_counts_by_device", lambda: {"ai": 2})
    monkeypatch.setattr(pipeline_metrics, "snapshot", lambda **_kwargs: {
        "in_flight_count": 1, "in_flight": [{"device_id": "ai"}],
        "failed_frames_in_window": 2, "throughput": {},
    })
    monkeypatch.setattr(pipeline_metrics, "agent_queues", lambda: [
        {"device_id": "ai", "queued_frames": 3, "age_seconds": 12},
    ])

    result = capture_status(db_session, None)  # type: ignore[arg-type]
    devices = {item.device_id: item for item in result.devices}

    for device_id, status, model, _tier, expected in definitions:
        assert devices[device_id].last_review_status == expected
        assert devices[device_id].classifier_status == status
        assert devices[device_id].review_model == model
    assert result.last_reviewed_at == (now - timedelta(minutes=7)).replace(tzinfo=None)
    assert devices["event-only"].last_review_status == "not_reviewed"
    assert devices["event-only"].last_reviewed_at is None
    assert devices["event-only"].waiting_upload_count is None
    assert devices["ai"].last_reviewed_at == (now - timedelta(minutes=10)).replace(tzinfo=None)
    assert devices["ai"].pending_review_count == 2
    assert devices["ai"].reviewing_count == 1
    assert devices["ai"].waiting_upload_count == 3
    assert devices["ai"].queue_report_age_seconds == 12
    assert result.review_failures_5m == 2
