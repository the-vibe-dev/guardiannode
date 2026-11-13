from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, Request

from app.api.child_requests import ChildRequestReview, review_child_request
from app.db.models import ChildRequest, User


def _request() -> Request:
    return Request({
        "type": "http", "method": "POST", "path": "/api/child-requests/r/review",
        "headers": [], "client": ("127.0.0.1", 1234), "scheme": "http",
        "server": ("testserver", 80),
    })


def test_retired_approvals_preserve_existing_request_history(db_session):
    user = User(display_name="Synthetic Parent", password_hash="test", recovery_hash="test")
    db_session.add(user)
    db_session.add(ChildRequest(
        request_id="open", request_type="more_time", status="open",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    ))
    db_session.add(ChildRequest(
        request_id="expired", request_type="more_time", status="open",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    ))
    db_session.commit()

    for request_id in ("open", "expired"):
        with pytest.raises(HTTPException) as retired:
            review_child_request(request_id, ChildRequestReview(status="approved"), _request(), db_session, user)
        assert retired.value.status_code == 410
    db_session.expire_all()
    assert db_session.get(ChildRequest, "open").status == "open"
    assert db_session.get(ChildRequest, "expired").status == "open"
