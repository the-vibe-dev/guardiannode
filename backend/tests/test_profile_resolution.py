"""Profile resolution must behave identically for screenshot and text ingest."""
from __future__ import annotations

import pytest

from app.db.models import ChildProfile, Device, Event, RiskResult
from app.services.profile_resolution import resolve_profile


def _mk_device(db, device_id="dev1", profile_id=None):
    d = Device(device_id=device_id, hostname="kid-pc", paired=True, profile_id=profile_id)
    db.add(d)
    db.commit()
    return d


def _mk_profile(db, profile_id="prof1", age_group="14_17", phrases=None):
    p = ChildProfile(
        profile_id=profile_id,
        display_name="Kid",
        age_group=age_group,
        custom_watch_phrases=phrases or [],
    )
    db.add(p)
    db.commit()
    return p


# ---- helper unit behavior ---------------------------------------------------

def test_payload_profile_wins_when_valid(db_session):
    _mk_profile(db_session, "prof1", phrases=["springfield middle"])
    _mk_profile(db_session, "prof2", age_group="under_10")
    _mk_device(db_session, profile_id="prof2")
    r = resolve_profile(db_session, device_id="dev1", payload_profile_id="prof1")
    assert r.profile_id == "prof1"
    assert r.age_group == "14_17"
    assert r.custom_phrases == ["springfield middle"]


def test_invalid_payload_profile_falls_back_to_device_assignment(db_session):
    _mk_profile(db_session, "prof2", age_group="under_10", phrases=["maple street"])
    _mk_device(db_session, profile_id="prof2")
    r = resolve_profile(db_session, device_id="dev1", payload_profile_id="nope")
    assert r.profile_id == "prof2"
    assert r.age_group == "under_10"
    assert r.custom_phrases == ["maple street"]


def test_device_assignment_used_when_payload_omits_profile(db_session):
    _mk_profile(db_session, "prof2", phrases=["soccer practice"])
    _mk_device(db_session, profile_id="prof2")
    r = resolve_profile(db_session, device_id="dev1")
    assert r.profile_id == "prof2"
    assert r.custom_phrases == ["soccer practice"]


def test_default_fallback_does_not_crash(db_session):
    _mk_device(db_session)
    r = resolve_profile(db_session, device_id="dev1")
    assert r.profile_id is None
    assert r.age_group == "10_13"
    assert r.custom_phrases == []
    # Unknown device id is also safe.
    r = resolve_profile(db_session, device_id="ghost")
    assert r.profile_id is None


def test_payload_age_group_honored_only_without_profile(db_session):
    _mk_device(db_session)
    r = resolve_profile(db_session, device_id="dev1", payload_age_group="14_17")
    assert r.age_group == "14_17"
    r = resolve_profile(db_session, device_id="dev1", payload_age_group="bogus")
    assert r.age_group == "10_13"


# ---- end-to-end: custom watch phrase works on both ingest paths -------------

@pytest.mark.asyncio
async def test_text_event_uses_device_assigned_profile_watch_phrase(db_session):
    _mk_profile(db_session, "prof1", phrases=["example middle school"])
    _mk_device(db_session, profile_id="prof1")

    from app.services import event_ingest

    result = await event_ingest.ingest_event(
        db_session,
        payload={
            "source_type": "ocr",
            "redacted_text": "meet me after example middle school tomorrow",
        },
        device_id="dev1",
    )
    db_session.commit()
    assert "custom_watch" in result["categories"]
    ev = db_session.get(Event, result["event_id"])
    assert ev.profile_id == "prof1"


@pytest.mark.asyncio
async def test_screenshot_path_uses_device_assigned_profile_watch_phrase(db_session, monkeypatch):
    _mk_profile(db_session, "prof1", phrases=["example middle school"])
    _mk_device(db_session, profile_id="prof1")

    from app.services import screenshot_ingest

    # text_only tier with a fake Tesseract so no LLM/vision call is needed.
    monkeypatch.setattr(screenshot_ingest.settings, "classifier_tier", "text_only")
    monkeypatch.setattr(
        screenshot_ingest, "_tesseract_extract",
        lambda b: "meet me after example middle school tomorrow",
    )

    async def fake_classify_text(**kwargs):
        from app.services import risk_rules
        matches = risk_rules.evaluate(kwargs["redacted_text"], custom_phrases=kwargs.get("custom_phrases"))
        return screenshot_ingest._rules_result_from_matches(matches) | {
            "model": None, "false_positive_notes": "", "prompt_version": None,
        }

    monkeypatch.setattr(screenshot_ingest.classifier, "classify_text", fake_classify_text)

    result = await screenshot_ingest.ingest_screenshot(
        db_session,
        image_bytes=b"\xff\xd8\xff\xe0fake",
        device_id="dev1",
    )
    db_session.commit()
    assert "custom_watch" in result["categories"]
    ev = db_session.get(Event, result["event_id"])
    assert ev.profile_id == "prof1"


@pytest.mark.asyncio
async def test_vision_only_tesseract_catches_watch_phrase_when_vision_ocr_is_empty(
    db_session, monkeypatch
):
    _mk_profile(db_session, "prof1", phrases=["Alex Example", "123 Example Street"])
    _mk_device(db_session, profile_id="prof1")

    from app.services import screenshot_ingest

    monkeypatch.setattr(screenshot_ingest.settings, "classifier_tier", "vision_only")

    async def fake_vision_available():
        return True, [screenshot_ingest.settings.vision_model]

    async def fake_classify_image(**kwargs):
        return {
            "visible_text": "",
            "risk_level": "none",
            "score": 0,
            "categories": [],
            "confidence": 0.0,
        }

    monkeypatch.setattr(screenshot_ingest, "_vision_available", fake_vision_available)
    monkeypatch.setattr(screenshot_ingest.image_safety, "classify_image", fake_classify_image)
    monkeypatch.setattr(
        screenshot_ingest,
        "_tesseract_extract",
        lambda b: "Customer: Alex Example\nAddress: 123 Example Street",
    )

    result = await screenshot_ingest.ingest_screenshot(
        db_session,
        image_bytes=b"\xff\xd8\xff\xe0fake",
        device_id="dev1",
        app_name="putty.exe",
    )
    db_session.commit()

    assert result["risk_level"] == "high"
    assert "custom_watch" in result["categories"]
    risk = db_session.get(RiskResult, result["risk_id"])
    assert set(risk.rules_triggered) == {
        "custom_watch:123 example street",
        "custom_watch:alex example",
    }


@pytest.mark.asyncio
async def test_invalid_payload_profile_cannot_override_device_assignment(db_session):
    _mk_profile(db_session, "prof1", phrases=["watchword"])
    _mk_device(db_session, profile_id="prof1")

    from app.services import event_ingest

    result = await event_ingest.ingest_event(
        db_session,
        payload={
            "source_type": "ocr",
            "redacted_text": "this contains the watchword right here",
            "profile_id": "spoofed-profile",
        },
        device_id="dev1",
    )
    db_session.commit()
    ev = db_session.get(Event, result["event_id"])
    assert ev.profile_id == "prof1"  # not the spoofed id
    assert "custom_watch" in result["categories"]
