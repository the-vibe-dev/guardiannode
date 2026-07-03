#!/usr/bin/env python3
"""Check source-controlled repository governance files for release readiness."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _require(path: str, needles: list[str], failures: list[str]) -> None:
    full_path = ROOT / path
    if not full_path.exists():
        failures.append(f"missing {path}")
        return
    text = full_path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            failures.append(f"{path}: missing {needle!r}")


def main() -> int:
    failures: list[str] = []
    _require(
        ".github/CODEOWNERS",
        [
            "/.github/",
            "/backend/app/services/encryption.py",
            "/agent-windows/src/durable_queue.py",
            "/installer/",
            "/SECURITY.md",
            "/PRIVACY.md",
        ],
        failures,
    )
    _require(
        ".github/dependabot.yml",
        [
            'package-ecosystem: "github-actions"',
            'package-ecosystem: "pip"',
            'directory: "/backend"',
            'directory: "/agent-windows"',
            'package-ecosystem: "npm"',
            'directory: "/dashboard"',
            'package-ecosystem: "docker"',
            'directory: "/installer/server-linux"',
        ],
        failures,
    )
    _require(
        "docs/REPOSITORY_CONTROLS.md",
        [
            "Require pull requests before merging",
            "Require review from CODEOWNERS",
            "Block force pushes",
            "Protect `v*` tags",
            "Enable GitHub secret scanning",
            "Enable push protection",
            "Enable private vulnerability reporting",
            "installer assets, if attached",
            "SmartScreen/Defender warning guidance",
        ],
        failures,
    )
    _require(
        "RELEASE_CHECKLIST.md",
        [
            "docs/REPOSITORY_CONTROLS.md",
            "signed or otherwise verified",
            "Installer hashes generated if installers are included",
            "SmartScreen/Defender",
        ],
        failures,
    )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("repository governance source files are present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
