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


def test_parent_decision_cannot_overwrite_or_approve_expired_request(db_session):
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

    decided = review_child_request("open", ChildRequestReview(status="approved"), _request(), db_session, user)
    assert decided.status == "approved"

    for request_id in ("open", "expired"):
        with pytest.raises(HTTPException) as conflict:
            review_child_request(request_id, ChildRequestReview(status="denied"), _request(), db_session, user)
        assert conflict.value.status_code == 409
    db_session.expire_all()
    assert db_session.get(ChildRequest, "open").status == "approved"
    assert db_session.get(ChildRequest, "expired").status == "open"
