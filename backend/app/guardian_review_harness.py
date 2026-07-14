"""Synthetic-only command-line harness for the complete Guardian Review path."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app import settings as settings_mod
from app.db.models import Alert, ChildProfile, Device, Event, RiskResult, User
from app.guardian_review_models import GuardianReviewContext
from app.services import encryption, guardian_review

SCENARIOS: dict[str, dict[str, Any]] = {
    "unknown-contact": {
        "text": "A person asks to move to a private chat and keep it secret.",
        "categories": ["grooming", "off_platform_contact", "secrecy_request"],
        "severity": "high",
        "score": 86,
    },
    "ambiguous-joke": {
        "text": "A fictional game chat contains an ambiguous threat used as a joke.",
        "categories": ["threat"],
        "severity": "medium",
        "score": 55,
    },
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Guardian Review using synthetic incidents only")
    parser.add_argument("--provider", choices=["mock", "codex", "openai"], default="mock")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="unknown-contact")
    parser.add_argument("--data-dir", type=Path, default=Path(".guardian-review-harness"))
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--confirm-live", action="store_true", help="Required for codex/openai providers")
    parser.add_argument("--fresh", action="store_true")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> dict:
    if args.provider != "mock" and not args.confirm_live:
        raise SystemExit("Live providers require --confirm-live")
    settings = settings_mod.Settings(
        data_dir=args.data_dir.resolve(),
        guardian_review_enabled=True,
        guardian_review_provider=args.provider,
        guardian_review_zdr_confirmed=args.provider == "openai",
        codex_home=args.codex_home.resolve(),
        mdns_enabled=False,
        retention_cleanup_enabled=False,
        device_offline_alert_enabled=False,
        notification_worker_enabled=False,
        database_backup_enabled=False,
    )
    settings_mod.settings = settings
    from app.db import session as session_mod
    session_mod._engine = None
    session_mod._SessionLocal = None
    encryption._reset_cache()
    from app.db.migrations import upgrade_schema
    from app.db.session import get_engine, get_sessionmaker
    upgrade_schema(get_engine())
    db = get_sessionmaker()()
    try:
        suffix = args.scenario.replace("-", "_")
        scenario = SCENARIOS[args.scenario]
        user = db.query(User).filter(User.display_name == "Synthetic Harness Parent").first()
        if user is None:
            user = User(display_name="Synthetic Harness Parent", password_hash="synthetic-not-usable", recovery_hash="synthetic-not-usable", role="admin")
            db.add(user)
            db.flush()
        profile_id = f"synthetic-profile-{suffix}"
        device_id = f"synthetic-device-{suffix}"
        event_id = f"synthetic-event-{suffix}"
        risk_id = f"synthetic-risk-{suffix}"
        alert_id = f"synthetic-alert-{suffix}"
        profile = db.get(ChildProfile, profile_id)
        if profile is None:
            db.add(ChildProfile(profile_id=profile_id, display_name="Synthetic Child", age_group="10_13", custom_watch_phrases=[]))
            db.add(Device(device_id=device_id, hostname="synthetic-device", platform="windows", paired=True, profile_id=profile_id))
            text = str(scenario["text"])
            db.add(Event(event_id=event_id, device_id=device_id, profile_id=profile_id, source_type="synthetic", timestamp=datetime.now(UTC), redacted_text_enc=encryption.encrypt_text(text)))
            db.add(RiskResult(risk_id=risk_id, event_id=event_id, risk_level=str(scenario["severity"]), score=int(scenario["score"]), categories=list(scenario["categories"]), summary=text, evidence=[text], recommended_action="parent_review", confidence=0.78, classifier_status="ok"))
            db.flush()
            db.add(Alert(alert_id=alert_id, risk_id=risk_id, device_id=device_id, profile_id=profile_id, severity=scenario["severity"], repeat_count=1))
            db.commit()
        context = GuardianReviewContext(
            relationship_context="unknown_person",
            repeated_behavior="unknown",
            parent_believes_immediate_danger=False,
            parent_goal="prepare_conversation",
            parent_context="Synthetic fixture only; no real family data.",
            fresh_assessment=args.fresh,
        )
        preview = guardian_review.create_preview(db, alert_id=alert_id, context=context, user=user)
        accepted = guardian_review.submit_review(db, alert_id=alert_id, preview_id=preview.preview_id, preview_digest=preview.preview_digest, user=user)
        await guardian_review.process_one(db)
        result = guardian_review.get_result(db, review_id=accepted.review_id, user=user)
        return {
            "scenario": args.scenario,
            "synthetic": True,
            "provider": args.provider,
            "data_dir": str(settings.data_dir),
            "preview": {"preview_id": preview.preview_id, "digest": preview.preview_digest, "redactions": preview.redactions_applied},
            "result": result.model_dump(mode="json"),
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    print(json.dumps(asyncio.run(_run(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
