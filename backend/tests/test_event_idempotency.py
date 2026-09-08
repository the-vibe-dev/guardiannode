from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import Alert, Device, Event, RiskResult
from app.services import event_ingest


@pytest.mark.asyncio
async def test_text_event_idempotency_returns_original_result_without_reclassification(db_session):
    db_session.add(Device(device_id="device-1", hostname="kid-pc", paired=True))
    db_session.flush()
    db_session.add(Event(
        event_id="event-1",
        device_id="device-1",
        source_type="visible_text",
        timestamp=datetime.now(UTC),
    ))
    db_session.flush()
    db_session.add(RiskResult(
        risk_id="risk-1",
        event_id="event-1",
        risk_level="high",
        score=88,
        categories=["grooming"],
    ))
    db_session.flush()
    db_session.add(Alert(
        alert_id="alert-1",
        risk_id="risk-1",
        device_id="device-1",
        severity="high",
    ))
    db_session.commit()

    result = await event_ingest.ingest_event(
        db_session,
        payload={"event_id": "event-1", "source_type": "visible_text", "redacted_text": "retry"},
        device_id="device-1",
    )
    assert result == {
        "event_id": "event-1",
        "risk_id": "risk-1",
        "alert_id": "alert-1",
        "risk_level": "high",
        "score": 88,
        "categories": ["grooming"],
    }
    assert db_session.query(Event).count() == 1


@pytest.mark.asyncio
async def test_text_event_idempotency_key_cannot_cross_devices(db_session):
    db_session.add_all([
        Device(device_id="device-1", hostname="one", paired=True),
        Device(device_id="device-2", hostname="two", paired=True),
    ])
    db_session.flush()
    db_session.add(Event(
        event_id="event-1",
        device_id="device-1",
        source_type="visible_text",
        timestamp=datetime.now(UTC),
    ))
    db_session.commit()

    with pytest.raises(ValueError, match="another device"):
        await event_ingest.ingest_event(
            db_session,
            payload={"event_id": "event-1", "source_type": "visible_text"},
            device_id="device-2",
        )
