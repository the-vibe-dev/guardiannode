from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dashboard import capture_status
from app.db.models import Device, ScreenshotUploadReceipt
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
