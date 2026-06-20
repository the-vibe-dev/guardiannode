from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models import Event


def test_sqlite_foreign_keys_enabled_for_sessions(db_session):
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    db_session.add(
        Event(
            event_id="event-with-missing-device",
            device_id="missing-device",
            source_type="browser",
            timestamp=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
