#!/usr/bin/env python3
"""Verify THIRD_PARTY_NOTICES.md acknowledges direct runtime dependencies."""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTICE = ROOT / "THIRD_PARTY_NOTICES.md"
ACK_RE = re.compile(r"<!-- third-party-notices:acknowledged(?P<body>.*?)-->", re.S)
REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.@/-]+)")
ALLOWED_EXTRA = {"inno-setup", "winsw", "pyinstaller", "ollama"}
OPTIONAL_RUNTIME_EXTRAS = {"agent": {"windows", "ocr"}}


def normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(" ", "-")


def requirement_name(requirement: str) -> str:
    match = REQ_NAME_RE.match(requirement)
    if not match:
        raise ValueError(f"Cannot parse requirement name from {requirement!r}")
    return normalize(match.group(1).split("[", 1)[0])


def pyproject_dependencies(path: Path, *, group: str) -> set[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    deps = {requirement_name(dep) for dep in project.get("dependencies", [])}
    for extra_name, extra_deps in project.get("optional-dependencies", {}).items():
        if extra_name in OPTIONAL_RUNTIME_EXTRAS.get(group, set()):
            deps.update(requirement_name(dep) for dep in extra_deps)
    return deps


def dashboard_dependencies(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {normalize(name) for name in data.get("dependencies", {})}


def acknowledged() -> dict[str, set[str]]:
    text = NOTICE.read_text(encoding="utf-8")
    match = ACK_RE.search(text)
    if not match:
        raise AssertionError("THIRD_PARTY_NOTICES.md is missing the acknowledged manifest")
    groups: dict[str, set[str]] = {}
    for raw_line in match.group("body").strip().splitlines():
        if not raw_line.strip():
            continue
        label, _, values = raw_line.partition(":")
        if not _:
            raise AssertionError(f"Malformed acknowledged notices line: {raw_line!r}")
        groups[normalize(label)] = {
            normalize(value)
            for value in values.split(",")
            if value.strip()
        }
    return groups


def main() -> int:
    groups = acknowledged()
    expected = {
        "backend": pyproject_dependencies(ROOT / "backend" / "pyproject.toml", group="backend"),
        "agent": pyproject_dependencies(ROOT / "agent-windows" / "pyproject.toml", group="agent"),
        "dashboard": dashboard_dependencies(ROOT / "dashboard" / "package.json"),
    }
    actual = {
        group: groups.get(group, set())
        for group in expected
    }
    errors: list[str] = []
    for group, expected_deps in expected.items():
        missing = expected_deps - actual[group]
        stale = actual[group] - expected_deps
        if missing:
            errors.append(f"{group}: missing notices for {', '.join(sorted(missing))}")
        if stale:
            errors.append(f"{group}: stale acknowledged dependencies {', '.join(sorted(stale))}")

    stale_other = groups.get("other", set()) - ALLOWED_EXTRA
    if stale_other:
        errors.append(f"other: unexpected acknowledgements {', '.join(sorted(stale_other))}")

    for license_file in (
        ROOT / "licenses" / "Inter-OFL-1.1.txt",
        ROOT / "licenses" / "Sora-OFL-1.1.txt",
    ):
        if not license_file.exists():
            errors.append(f"missing bundled font license: {license_file.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("third-party notices match direct dependency manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
