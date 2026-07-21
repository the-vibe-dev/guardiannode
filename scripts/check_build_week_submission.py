#!/usr/bin/env python3
"""Validate the local Build Week submission package without external accounts.

This check intentionally does not claim to validate a Windows installation,
OpenAI credentials, YouTube visibility, Devpost submission, or a Codex feedback
session. Those gates require the maintainer and are tracked in the submission
checklist.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    ".env.example",
    "BUILD_WEEK.md",
    "docs/build-week/BASELINE.md",
    "docs/build-week/CHANGELOG.md",
    "docs/build-week/DEVPOST_DRAFT.md",
    "docs/build-week/EVALUATION_RESULTS.md",
    "docs/build-week/FINAL_SUBMISSION_REVIEW.md",
    "docs/build-week/SUBMISSION_CHECKLIST.md",
    "docs/build-week/VIDEO_SCRIPT.md",
    "docs/build-week/video/CAPTIONS.srt",
    "docs/build-week/video/CODEX_COMPUTER_PROMPT.md",
    "docs/build-week/video/SHOT_MANIFEST.json",
    "docs/build-week/video/VIDEO_PRODUCTION_RUNBOOK.md",
    "docs/build-week/video/VOICEOVER.txt",
    "docs/build-week/video/YOUTUBE_COPY.md",
)

README_EVIDENCE = (
    "What GuardianNode is",
    "What Guardian Review adds",
    "Existing-project disclosure",
    "Claude-assisted",
    "How Codex is being used",
    "How GPT-5.6 is used at runtime",
    "pre-build-week-2026",
    "Architecture and privacy flow",
    "Demo mode",
    "Live mode",
    "Tests and evaluation",
    "Supported platforms",
    "License",
)

DEVPOST_EVIDENCE = (
    "Apps for Your Life",
    "Problem",
    "Solution",
    "How it works",
    "How Codex was used",
    "How GPT-5.6 was used",
    "Existing-project / Build Week disclosure",
    "Challenges",
    "Accomplishments",
    "What we learned",
    "Next steps",
    "Repository and judge instructions",
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SRT_TIMESTAMP = re.compile(r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})")


def _tracked_markdown() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def _check_local_links(paths: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip().split()[0].strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            if not resolved.exists():
                failures.append(f"{path.relative_to(ROOT)} -> {target_path}")
    return failures


def _last_caption_seconds(path: Path) -> float:
    stamps = list(SRT_TIMESTAMP.finditer(path.read_text(encoding="utf-8")))
    if not stamps:
        raise ValueError("caption file contains no timestamps")
    stamp = stamps[-1]
    return (
        int(stamp["h"]) * 3600
        + int(stamp["m"]) * 60
        + int(stamp["s"])
        + int(stamp["ms"]) / 1000
    )


def validate() -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            failures.append(f"missing required file: {relative}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in README_EVIDENCE:
        if phrase not in readme:
            failures.append(f"README missing required evidence: {phrase}")

    devpost = (ROOT / "docs/build-week/DEVPOST_DRAFT.md").read_text(encoding="utf-8")
    for phrase in DEVPOST_EVIDENCE:
        if phrase not in devpost:
            failures.append(f"Devpost draft missing section/evidence: {phrase}")

    manifest_path = ROOT / "docs/build-week/video/SHOT_MANIFEST.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            runtime = int(manifest["target_runtime_seconds"])
            if not 155 <= runtime <= 170:
                failures.append(f"video target must be 155-170 seconds, got {runtime}")
            if len(manifest.get("shots", [])) < 7:
                failures.append("video manifest must include at least seven functional shots")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"invalid video shot manifest: {exc}")

    captions_path = ROOT / "docs/build-week/video/CAPTIONS.srt"
    if captions_path.exists():
        try:
            caption_runtime = _last_caption_seconds(captions_path)
            if not 155 <= caption_runtime <= 170:
                failures.append(
                    f"caption runtime must be 155-170 seconds, got {caption_runtime:.3f}"
                )
        except ValueError as exc:
            failures.append(str(exc))

    tracked = _tracked_markdown()
    failures.extend(f"broken local Markdown link: {item}" for item in _check_local_links(tracked))

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if version != "0.1.0-alpha.3":
        failures.append(f"unexpected submission version: {version}")

    try:
        tag_commit = subprocess.run(
            ["git", "rev-list", "-n", "1", "pre-build-week-2026"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if tag_commit != "36b2a547056d40eff32f00aa59b7820f7d3e98d5":
            failures.append(f"baseline tag resolves to unexpected commit: {tag_commit}")
    except subprocess.CalledProcessError:
        failures.append("baseline tag pre-build-week-2026 is missing")

    warnings.extend(
        [
            "real Windows node qualification remains manual",
            "live GPT-5.6 run requires approved account configuration and remains manual",
            "YouTube/Devpost visibility and /feedback session ID remain external gates",
        ]
    )
    return {
        "status": "passed" if not failures else "failed",
        "version": version,
        "failures": failures,
        "manual_gates": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()
    result = validate()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Build Week submission check: {result['status']}")
        for failure in result["failures"]:
            print(f"FAIL: {failure}")
        for gate in result["manual_gates"]:
            print(f"MANUAL: {gate}")
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
