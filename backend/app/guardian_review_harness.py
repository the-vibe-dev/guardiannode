"""Synthetic-only command-line harness for the complete Guardian Review path."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app import settings as settings_mod
from app.db.models import Alert, ChildProfile, Device, Event, RiskResult, User
from app.demo_scenarios import SCENARIOS as DEMO_SCENARIOS
from app.guardian_review_models import GuardianReviewContext
from app.services import encryption, guardian_review
from app.services.classifier import classify_text

SCENARIOS = {scenario["id"]: scenario for scenario in DEMO_SCENARIOS}
SCENARIO_ALIASES = {
    "unknown-contact": "unknown-contact-secrecy",
    "ambiguous-joke": "ambiguous-gaming-language",
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Guardian Review using synthetic incidents only")
    parser.add_argument("--provider", choices=["mock", "codex", "openai"], default="mock")
    parser.add_argument(
        "--scenario",
        choices=sorted([*SCENARIOS, *SCENARIO_ALIASES]),
        default="unknown-contact-secrecy",
    )
    parser.add_argument("--data-dir", type=Path, default=Path(".guardian-review-harness"))
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--confirm-live", action="store_true", help="Required for codex/openai providers")
    parser.add_argument(
        "--confirm-zdr",
        action="store_true",
        help="Required for OpenAI after verifying the selected project's ZDR controls",
    )
    parser.add_argument("--fresh", action="store_true")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> dict:
    if args.provider != "mock" and not args.confirm_live:
        raise SystemExit("Live providers require --confirm-live")
    if args.provider == "openai" and not getattr(args, "confirm_zdr", False):
        raise SystemExit("OpenAI live mode requires --confirm-zdr after verifying project controls")
    settings = settings_mod.Settings(
        data_dir=args.data_dir.resolve(),
        guardian_review_enabled=True,
        guardian_review_provider=args.provider,
        guardian_review_zdr_confirmed=getattr(args, "confirm_zdr", False),
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
        scenario_id = SCENARIO_ALIASES.get(args.scenario, args.scenario)
        suffix = scenario_id.replace("-", "_")
        scenario = SCENARIOS[scenario_id]
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
            db.add(ChildProfile(profile_id=profile_id, display_name="Synthetic Child", age_group=scenario["age_group"], custom_watch_phrases=[]))
            db.add(Device(device_id=device_id, hostname="synthetic-device", platform="windows", paired=True, profile_id=profile_id))
            db.flush()
            text = str(scenario["text"])
            local = await classify_text(
                redacted_text=text,
                app_name="GuardianNode Synthetic Harness",
                source_type="synthetic",
                age_group=scenario["age_group"],
                use_llm=False,
            )
            db.add(Event(event_id=event_id, device_id=device_id, profile_id=profile_id, source_type="synthetic", timestamp=datetime.now(UTC), redacted_text_enc=encryption.encrypt_text(text), event_metadata={"synthetic": True, "scenario_id": scenario_id}))
            db.flush()
            db.add(RiskResult(risk_id=risk_id, event_id=event_id, risk_level=local["risk_level"], score=local["score"], categories=local["categories"], summary=local["summary"] or "No local rule matched this synthetic control scenario.", evidence=local["evidence"] or ["No deterministic safety rule matched."], recommended_action=local["recommended_action"], model=local["model"], rules_triggered=local["rules_triggered"], confidence=local["confidence"], false_positive_notes="Synthetic harness scenario", prompt_version=local["prompt_version"], rules_version=local["rules_version"], classifier_status=local["status"]))
            db.flush()
            db.add(Alert(alert_id=alert_id, risk_id=risk_id, device_id=device_id, profile_id=profile_id, severity=local["risk_level"], repeat_count=1))
            db.commit()
        context = GuardianReviewContext(
            relationship_context=scenario["relationship_context"],
            repeated_behavior=scenario["repeated_behavior"],
            parent_believes_immediate_danger=False,
            parent_goal=scenario["parent_goal"],
            parent_context="Synthetic fixture only; no real family data.",
            fresh_assessment=args.fresh,
        )
        preview = guardian_review.create_preview(db, alert_id=alert_id, context=context, user=user)
        accepted = guardian_review.submit_review(db, alert_id=alert_id, preview_id=preview.preview_id, preview_digest=preview.preview_digest, user=user)
        await guardian_review.process_one(db)
        result = guardian_review.get_result(db, review_id=accepted.review_id, user=user)
        return {
            "scenario": scenario_id,
            "synthetic": True,
            "output_redacted": True,
            "provider": args.provider,
            "data_dir": "[local harness directory]",
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
