"""Privacy choices govern actual processing, including work already queued."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from ulid import ULID

from app.db.models import AuditLog, ConsentRecord, Device, Event, EvidenceBlob, GuardianReview, User
from app.db.session import get_sessionmaker
from app.services import classifier, consent, event_ingest, guardian_review, notifications
from tests.test_input_bounds import _paired_token
from tests.test_notification_reliability import _configure, _job
from tests.test_purge_cascade import _mk_chain
from tests.test_readiness_apis import _client as _parent_client


def _client(monkeypatch, tmp_path):
    parent = _parent_client(monkeypatch, tmp_path)
    # Exercise the real loopback-only bootstrap contract while retaining the
    # parent's setup session; never bypass device authentication in these tests.
    client = TestClient(parent.app, client=("127.0.0.1", 50000))
    client.cookies.update(parent.cookies)
    client.headers.update(parent.headers)
    parent.close()
    return client


def _choices(**overrides):
    return {
        "screenshots": True, "apps_and_urls": True, "retention": True,
        "notifications": True, "external_ai": False, "child_notice_acknowledged": True,
        **overrides,
    }


def _grant(client, **overrides):
    response = client.post("/api/consent", json={
        "notice_version": consent.NOTICE_VERSION, "choices": _choices(**overrides),
    })
    assert response.status_code == 200, response.text


def _family(db, **overrides):
    user = db.query(User).first()
    if user is None:
        user = User(display_name="Synthetic parent", password_hash="test-only", recovery_hash="test-only")
        db.add(user)
        db.flush()
    db.add(ConsentRecord(
        consent_id=str(ULID()), user_id=user.id, notice_version=consent.NOTICE_VERSION,
        status="granted", choices=_choices(**overrides),
    ))
    db.commit()


def test_capture_policy_remains_disabled_before_parent_setup(monkeypatch, tmp_path):
    from tests.test_input_bounds import _client as bootstrap_client

    client = bootstrap_client(monkeypatch, tmp_path)
    token = _paired_token(client)
    result = client.get("/api/devices/capture-config", headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 200
    assert result.json()["monitoring_enabled"] is False
    text = client.post("/api/events", headers={"Authorization": f"Bearer {token}"}, json={
        "source_type": "browser", "redacted_text": "Pre-setup synthetic text",
    })
    assert text.status_code == 403
    frame = client.post("/api/events/screenshot", headers={"Authorization": f"Bearer {token}"},
                        files={"image": ("unused.png", b"not decoded", "image/png")})
    assert frame.status_code == 200
    assert frame.json()["queued"] is False


@pytest.mark.parametrize("choice", ["screenshots", "retention"])
def test_screenshot_opt_out_disables_capture_and_writes_no_pending_bytes(monkeypatch, tmp_path, choice):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    token = _paired_token(client)
    _grant(client, **{choice: False})
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/devices/capture-config", headers=auth).json()["monitoring_enabled"] is False
    from app.services import screenshot_async
    monkeypatch.setattr(screenshot_async, "store_pending", lambda *a, **k: pytest.fail("Evidence must not be stored"))
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    response = client.post("/api/events/screenshot", headers=auth, files={"image": ("synthetic.png", image.getvalue(), "image/png")})
    assert response.status_code == 200, response.text
    assert response.json()["queued"] is False
    assert response.json()["status"] == "privacy_disabled"


def test_retention_opt_out_rejects_text_collection(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    token = _paired_token(client)
    _grant(client, retention=False)
    response = client.post("/api/events", headers={"Authorization": f"Bearer {token}"}, json={
        "source_type": "browser", "redacted_text": "Synthetic text",
    })
    assert response.status_code == 403
    with get_sessionmaker()() as db:
        assert db.query(Event).count() == 0


def _pending_files(tmp_path):
    paths = []
    for folder in ("pending", "pending_dead_letter"):
        directory = tmp_path / folder
        directory.mkdir(exist_ok=True)
        token = str(ULID())
        for suffix in (".enc", ".json"):
            path = directory / f"{token}{suffix}"
            path.write_bytes(b"synthetic bytes")
            paths.append(path)
    return paths


def test_withdraw_and_delete_removes_pending_and_retained_evidence(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    paths = _pending_files(tmp_path)
    with get_sessionmaker()() as db:
        _, _, _, blob = _mk_chain(db, tmp_path, suffix="withdraw", severity="high", age_days=0)
    response = client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    assert response.status_code == 200
    assert response.json()["active"] is False
    deletion = response.json()["deletion"]
    assert deletion["events"] == 1 and deletion["blobs"] == 1
    assert deletion["remaining_events"] == deletion["remaining_blobs"] == 0
    assert deletion["pending_captures"] == {"deleted": 4, "failed": 0}
    assert not any(path.exists() for path in [*paths, blob])
    with get_sessionmaker()() as db:
        assert db.query(Event).count() == db.query(EvidenceBlob).count() == 0
        assert all(not d.paired and d.token_hash is None for d in db.query(Device).all())
        assert db.query(AuditLog).filter_by(action="consent.pending_evidence_purge").count() == 1


def test_withdrawal_reports_partial_deletion_and_allows_retry(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    paths = _pending_files(tmp_path)
    with get_sessionmaker()() as db:
        _, _, _, blob = _mk_chain(db, tmp_path, suffix="locked", severity="high", age_days=0)
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path in (blob, paths[0]):
            raise PermissionError("synthetic locked evidence")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    response = client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    assert response.status_code == 200 and response.json()["active"] is False
    deletion = response.json()["deletion"]
    assert deletion["remaining_events"] == deletion["remaining_blobs"] == 1
    assert deletion["pending_captures"] == {"deleted": 3, "failed": 1}
    assert blob.exists() and paths[0].exists()
    monkeypatch.setattr(Path, "unlink", unlink)
    retried = client.post("/api/consent/withdraw", json={"evidence_disposition": "delete"})
    assert retried.status_code == 200
    result = retried.json()["deletion"]
    assert result["remaining_events"] == result["remaining_blobs"] == 0
    assert result["pending_captures"] == {"deleted": 1, "failed": 0}
    assert not blob.exists() and not paths[0].exists()


def test_withdrawal_during_pending_write_discards_late_capture(monkeypatch, tmp_path):
    from app.services import screenshot_async

    client = _client(monkeypatch, tmp_path)
    _grant(client)
    token = _paired_token(client)
    real_store = screenshot_async.store_pending

    def withdraw_then_store(image_bytes, meta):
        with get_sessionmaker()() as db:
            parent = db.query(User).first()
            db.add(ConsentRecord(
                consent_id=str(ULID()), user_id=parent.id,
                notice_version=consent.NOTICE_VERSION, status="withdrawn", choices={},
            ))
            for device in db.query(Device).all():
                device.paired = False
                device.token_hash = None
            db.commit()
        screenshot_async.purge_pending_capture_files()
        return real_store(image_bytes, meta)

    monkeypatch.setattr(screenshot_async, "store_pending", withdraw_then_store)
    monkeypatch.setattr(screenshot_async, "enqueue_nowait", lambda *_: pytest.fail("Late capture enqueued"))
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    response = client.post("/api/events/screenshot", headers={"Authorization": f"Bearer {token}"},
                           files={"image": ("synthetic.png", image.getvalue(), "image/png")})
    assert response.status_code == 200
    assert response.json()["status"] == "privacy_disabled"
    assert response.json()["queued"] is False
    assert list((tmp_path / "pending").iterdir()) == []


@pytest.mark.asyncio
async def test_context_opt_out_removes_separate_app_url_and_caller_metadata(db_session, monkeypatch):
    _family(db_session, apps_and_urls=False)
    db_session.add(Device(device_id="device-privacy", hostname="synthetic", paired=True))
    db_session.commit()
    classify = classifier.classify_text

    async def local_only(**kwargs):
        assert kwargs["app_name"] is None and kwargs["url"] is None
        return await classify(**kwargs, use_llm=False)

    monkeypatch.setattr(classifier, "classify_text", local_only)
    result = await event_ingest.ingest_event(db_session, device_id="device-privacy", payload={
        "source_type": "browser", "app_name": "sensitive-app.exe",
        "window_title": "private title", "url": "https://private.example.test/path",
        "redacted_text": "ordinary synthetic message",
        "metadata": {"nested": {"url": "https://private.example.test"}},
    })
    db_session.commit()
    event = db_session.get(Event, result["event_id"])
    assert event.app_name is event.window_title is event.url is None
    assert "private.example" not in json.dumps(event.event_metadata)


@pytest.mark.asyncio
async def test_retention_change_during_text_classification_prevents_persistence(db_session, monkeypatch):
    _family(db_session)
    db_session.add(Device(device_id="device-privacy", hostname="synthetic", paired=True))
    db_session.commit()
    classify = classifier.classify_text

    async def change_choices(**kwargs):
        _family(db_session, retention=False)
        return await classify(**kwargs, use_llm=False)

    monkeypatch.setattr(classifier, "classify_text", change_choices)
    with pytest.raises(PermissionError, match="permission changed"):
        await event_ingest.ingest_event(db_session, device_id="device-privacy", payload={
            "source_type": "browser", "redacted_text": "ordinary synthetic text",
        })
    assert db_session.query(Event).count() == 0


def test_queued_notifications_respect_current_opt_out(db_session, monkeypatch):
    _family(db_session)
    _configure(db_session, host="smtp.example.test")
    job = _job(db_session, "privacy")
    _family(db_session, notifications=False)
    monkeypatch.setattr(notifications, "_send_email", lambda *a, **k: pytest.fail("Opted-out transport invoked"))
    notifications.process_pending(db_session)
    assert job.status == "skipped"


@pytest.mark.asyncio
async def test_external_ai_requires_global_choice_and_rechecks_at_delivery(monkeypatch, tmp_path):
    from app import settings as settings_mod
    from tests.test_guardian_review import _client as review_client

    client = review_client(monkeypatch, tmp_path)
    settings_mod.settings.guardian_review_provider = "openai"
    monkeypatch.setattr(guardian_review, "_ensure_provider_ready", lambda _provider: None)
    _grant(client, external_ai=False)
    response = client.post("/api/alerts/alert-1/guardian-review/preview", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "external_ai_not_allowed"
    _grant(client, external_ai=True)
    response = client.post("/api/alerts/alert-1/guardian-review/preview", json={})
    assert response.status_code == 200, response.text
    preview = response.json()
    request = {"preview_id": preview["preview_id"], "preview_digest": preview["preview_digest"], "consent": True}
    _grant(client, external_ai=False)
    refused = client.post("/api/alerts/alert-1/guardian-review", json=request)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "consent_changed"
    _grant(client, external_ai=True)
    response = client.post("/api/alerts/alert-1/guardian-review/preview", json={})
    assert response.status_code == 200, response.text
    preview = response.json()
    request = {"preview_id": preview["preview_id"], "preview_digest": preview["preview_digest"], "consent": True}
    accepted = client.post("/api/alerts/alert-1/guardian-review", json=request)
    assert accepted.status_code == 202
    _grant(client, external_ai=False)

    class NeverSend:
        async def assess(self, **kwargs):
            pytest.fail("Opted-out external provider invoked")

    with get_sessionmaker()() as db:
        assert await guardian_review.process_one(db, provider_override=NeverSend())
        row = db.get(GuardianReview, accepted.json()["review_id"])
        assert row.status == "failed"
        assert row.error_code == "consent_changed"
