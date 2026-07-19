"""Parent-controlled synthetic demo flow for judges and local development."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import settings as settings_mod
from app.api.deps import get_db_dep, parent_user, require_critical_auth, require_recent_auth
from app.db.models import (
    Alert,
    ChildProfile,
    Device,
    Event,
    GuardianReview,
    GuardianReviewFeedback,
    GuardianReviewPreview,
    RiskResult,
    User,
)
from app.demo_scenarios import DEMO_VERSION, SCENARIOS, public_scenario, scenario_by_id
from app.services import encryption
from app.services import guardian_review as guardian_review_workflow
from app.services.audit import log_action
from app.services.classifier import classify_text

router = APIRouter(prefix="/demo", tags=["demo"])
_DEVICE_ID = "demo-device"
_PROFILE_ID = "demo-profile"


def _require_enabled() -> None:
    if not settings_mod.settings.demo_mode_enabled:
        raise HTTPException(status_code=404, detail="Demo mode is not enabled")


@router.get("/status")
def status(_: User = Depends(parent_user)) -> dict:
    readiness = guardian_review_workflow.provider_readiness(
        settings_mod.settings.guardian_review_provider
    )
    return {
        "enabled": settings_mod.settings.demo_mode_enabled,
        "synthetic_only": True,
        "demo_version": DEMO_VERSION,
        "device": {"device_id": _DEVICE_ID, "status": "demo_ready"},
        "guardian_review": {
            "provider": settings_mod.settings.guardian_review_provider,
            "model": guardian_review_workflow.configured_model(
                settings_mod.settings.guardian_review_provider
            ),
            "ready": readiness["ready"],
            "blocking_reason": readiness.get("blocking_reason"),
        },
    }


@router.get("/scenarios")
def scenarios(_: User = Depends(parent_user)) -> list[dict]:
    _require_enabled()
    return [public_scenario(scenario) for scenario in SCENARIOS]


@router.post("/scenarios/{scenario_id}/trigger")
async def trigger(
    scenario_id: str,
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
    _: None = Depends(require_recent_auth),
) -> dict:
    _require_enabled()
    scenario = scenario_by_id(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Synthetic scenario not found")

    now = datetime.now(UTC)
    suffix = uuid4().hex
    profile = db.get(ChildProfile, _PROFILE_ID)
    if profile is None:
        profile = ChildProfile(
            profile_id=_PROFILE_ID,
            display_name="Synthetic Demo Child",
            age_group=scenario["age_group"],
            notes="Synthetic Build Week demo profile; contains no real child data.",
        )
        db.add(profile)
    else:
        profile.age_group = scenario["age_group"]
    device = db.get(Device, _DEVICE_ID)
    if device is None:
        device = Device(
            device_id=_DEVICE_ID,
            hostname="synthetic-demo-device",
            platform="windows",
            agent_version="demo",
            paired=True,
            status="online",
            profile_id=_PROFILE_ID,
        )
        db.add(device)
    device.status = "online"
    device.last_seen = now
    db.flush()

    result = await classify_text(
        redacted_text=scenario["text"],
        app_name="GuardianNode Synthetic Demo",
        source_type="synthetic_demo",
        age_group=scenario["age_group"],
        timestamp=now.isoformat(),
        use_llm=False,
    )
    if result["risk_level"] != scenario["expected_local_severity"]:
        raise HTTPException(status_code=500, detail="Synthetic scenario classifier expectation changed")

    event_id = f"demo-event-{suffix}"
    risk_id = f"demo-risk-{suffix}"
    alert_id = f"demo-alert-{suffix}"
    db.add(
        Event(
            event_id=event_id,
            device_id=_DEVICE_ID,
            profile_id=_PROFILE_ID,
            source_type="synthetic_demo",
            app_name="GuardianNode Synthetic Demo",
            window_title=scenario["title"],
            timestamp=now,
            redacted_text_enc=encryption.encrypt_text(scenario["text"]),
            evidence_type="synthetic_text",
            event_metadata={
                "synthetic": True,
                "demo_version": DEMO_VERSION,
                "scenario_id": scenario_id,
                "relationship_context": scenario["relationship_context"],
                "repeated_behavior": scenario["repeated_behavior"],
                "parent_goal": scenario["parent_goal"],
            },
        )
    )
    db.flush()
    summary = result["summary"] or "No local rule matched this synthetic control scenario."
    db.add(
        RiskResult(
            risk_id=risk_id,
            event_id=event_id,
            risk_level=result["risk_level"],
            score=result["score"],
            categories=result["categories"],
            summary=summary,
            evidence=result["evidence"] or ["No deterministic safety rule matched."],
            recommended_action=result["recommended_action"],
            model=result["model"],
            rules_triggered=result["rules_triggered"],
            confidence=result["confidence"],
            false_positive_notes="Synthetic demo scenario",
            prompt_version=result["prompt_version"],
            rules_version=result["rules_version"],
            classifier_status=result["status"],
        )
    )
    db.flush()
    db.add(
        Alert(
            alert_id=alert_id,
            risk_id=risk_id,
            device_id=_DEVICE_ID,
            profile_id=_PROFILE_ID,
            severity=result["risk_level"],
            status="open",
            created_at=now,
            last_seen_at=now,
        )
    )
    log_action(
        db,
        actor=str(user.id),
        action="demo.scenario_triggered",
        target=alert_id,
        details={
            "synthetic": True,
            "scenario_id": scenario_id,
            "demo_version": DEMO_VERSION,
            "local_severity": result["risk_level"],
            "rules_triggered": result["rules_triggered"],
        },
    )
    db.commit()
    return {
        "synthetic": True,
        "scenario_id": scenario_id,
        "alert_id": alert_id,
        "alert_url": f"/alerts/{alert_id}",
        "local_detection": {
            "severity": result["risk_level"],
            "categories": result["categories"],
            "rules_triggered": result["rules_triggered"],
        },
    }


@router.post("/reset")
def reset(
    db: Session = Depends(get_db_dep),
    user: User = Depends(parent_user),
    _: None = Depends(require_critical_auth),
) -> dict:
    _require_enabled()
    scenario_ids = {scenario["id"] for scenario in SCENARIOS}
    event_ids = []
    for event in db.query(Event).filter(Event.event_id.like("demo-event-%")).all():
        metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
        if (
            event.device_id == _DEVICE_ID
            and event.profile_id == _PROFILE_ID
            and metadata.get("synthetic") is True
            and metadata.get("demo_version") == DEMO_VERSION
            and metadata.get("scenario_id") in scenario_ids
        ):
            event_ids.append(event.event_id)
    risk_ids = [
        row[0]
        for row in db.query(RiskResult.risk_id)
        .filter(RiskResult.event_id.in_(event_ids))
        .all()
    ] if event_ids else []
    alert_ids = [
        row[0]
        for row in db.query(Alert.alert_id).filter(Alert.risk_id.in_(risk_ids)).all()
    ] if risk_ids else []
    review_ids = [
        row[0]
        for row in db.query(GuardianReview.review_id)
        .filter(GuardianReview.alert_id.in_(alert_ids))
        .all()
    ] if alert_ids else []

    if review_ids:
        db.query(GuardianReviewFeedback).filter(
            GuardianReviewFeedback.review_id.in_(review_ids)
        ).delete(synchronize_session=False)
        db.query(GuardianReview).filter(GuardianReview.review_id.in_(review_ids)).delete(
            synchronize_session=False
        )
    if alert_ids:
        db.query(GuardianReviewPreview).filter(
            GuardianReviewPreview.alert_id.in_(alert_ids)
        ).delete(synchronize_session=False)
        db.query(Alert).filter(Alert.alert_id.in_(alert_ids)).delete(synchronize_session=False)
    if risk_ids:
        db.query(RiskResult).filter(RiskResult.risk_id.in_(risk_ids)).delete(
            synchronize_session=False
        )
    if event_ids:
        db.query(Event).filter(Event.event_id.in_(event_ids)).delete(synchronize_session=False)
    db.flush()
    if db.query(Event).filter(Event.device_id == _DEVICE_ID).count() == 0:
        db.query(Device).filter(Device.device_id == _DEVICE_ID).delete(synchronize_session=False)
    if (
        db.query(Event).filter(Event.profile_id == _PROFILE_ID).count() == 0
        and db.query(Device).filter(Device.profile_id == _PROFILE_ID).count() == 0
    ):
        db.query(ChildProfile).filter(ChildProfile.profile_id == _PROFILE_ID).delete(
            synchronize_session=False
        )
    log_action(
        db,
        actor=str(user.id),
        action="demo.reset",
        target=DEMO_VERSION,
        details={"synthetic": True, "alerts_removed": len(alert_ids)},
    )
    db.commit()
    return {"ok": True, "alerts_removed": len(alert_ids)}
