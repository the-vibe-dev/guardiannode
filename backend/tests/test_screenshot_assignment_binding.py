"""Accepted screenshots cannot silently move between children's review feeds."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app import settings as settings_mod
from app.db.models import Base, ChildProfile, Device, Event
from app.db.session import get_engine, get_sessionmaker
from app.services import screenshot_async, screenshot_ingest
from tests.test_consent_enforcement import _client, _grant
from tests.test_input_bounds import _paired_token


def _profiles(db):
    db.add_all([
        ChildProfile(profile_id="child-a", display_name="Child A", age_group="10_13"),
        ChildProfile(profile_id="child-b", display_name="Child B", age_group="under_10"),
    ])
    db.flush()


def _image():
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    return {"image": ("synthetic.png", image.getvalue(), "image/png")}


@pytest.mark.parametrize("change_during_write", [False, True])
def test_acceptance_binds_authoritative_assignment_and_rejects_changes_during_write(monkeypatch, tmp_path, change_during_write):
    client = _client(monkeypatch, tmp_path)
    _grant(client)
    token = _paired_token(client)
    with get_sessionmaker()() as db:
        _profiles(db)
        db.query(Device).one().profile_id = "child-a"
        db.commit()

    original = screenshot_async.store_pending
    observed = []

    def store(image, metadata):
        pending_token = original(image, metadata)
        observed.append(pending_token)
        if change_during_write:
            with get_sessionmaker()() as other:
                other.query(Device).one().profile_id = "child-b"
                other.commit()
        return pending_token

    monkeypatch.setattr(screenshot_async, "store_pending", store)
    queued = []
    monkeypatch.setattr(screenshot_async, "enqueue_nowait", lambda item: queued.append(item) or True)
    response = client.post(
        "/api/events/screenshot", headers={"Authorization": f"Bearer {token}"},
        data={"profile_id": "child-b"}, files=_image(),
    )
    assert len(observed) == 1
    if change_during_write:
        assert response.status_code == 409
        assert queued == []
        assert screenshot_async._load_meta(observed[0]) is None
        assert screenshot_async.pending_count() == 0
    else:
        assert response.status_code == 200, response.text
        assert response.json()["queued"] is True
        metadata = screenshot_async._load_meta(response.json()["event_id"])
        assert metadata["assigned_profile_id"] == "child-a"
        assert metadata["profile_id"] == "child-b", "Caller hint cannot replace authoritative receipt binding"
        assert queued == observed


@pytest.mark.asyncio
@pytest.mark.parametrize("bound,changed", [(True, "before_worker"), (True, "during_handoff"), (True, "unchanged"), (False, "before_worker")])
async def test_worker_validates_assignment_binding_and_explicit_legacy_compatibility(monkeypatch, bound, changed):
    monkeypatch.setattr(settings_mod.settings, "classifier_mode", "rules_only")
    monkeypatch.setattr(screenshot_ingest, "settings", settings_mod.settings)
    Base.metadata.create_all(get_engine())
    with get_sessionmaker()() as db:
        _profiles(db)
        db.add(Device(device_id="capture-device", hostname="synthetic", paired=True, profile_id="child-a"))
        db.commit()
    metadata = {"device_id": "capture-device"}
    if bound:
        metadata["assigned_profile_id"] = "child-a"
    token = screenshot_async.store_pending(b"synthetic frame", metadata)
    def reassign():
        with get_sessionmaker()() as db:
            db.get(Device, "capture-device").profile_id = "child-b"
            db.commit()
    if changed == "before_worker":
        reassign()
    elif changed == "during_handoff":
        original_ingest = screenshot_ingest.ingest_screenshot

        async def reassigned_before_ingest(*args, **kwargs):
            reassign()
            # Simulate the parent update between the worker's early read and
            # ingest's authoritative recheck, including a cached ORM Device.
            return await original_ingest(*args, **kwargs)

        monkeypatch.setattr(screenshot_ingest, "ingest_screenshot", reassigned_before_ingest)
    observed = []

    def extract(_image):
        observed.append(True)
        return "ordinary synthetic screen"

    monkeypatch.setattr(screenshot_ingest, "_tesseract_extract", extract)
    await screenshot_async._classify_token(token)
    with get_sessionmaker()() as db:
        if bound and changed != "unchanged":
            assert observed == []
            assert db.query(Event).count() == 0
        else:
            assert observed == [True]
            assert db.query(Event).one().profile_id == ("child-b" if changed != "unchanged" else "child-a")
    assert screenshot_async._load_meta(token) is None
    assert screenshot_async.pending_count() == 0
