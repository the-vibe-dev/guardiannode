#!/usr/bin/env python3
"""Check that package/installer versions agree with VERSION."""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pep440(version: str) -> str:
    match = re.fullmatch(r"(\d+\.\d+\.\d+)-alpha\.(\d+)", version)
    if match:
        return f"{match.group(1)}a{match.group(2)}"
    return version


def _read_toml_version(path: str) -> str:
    return tomllib.loads((ROOT / path).read_text(encoding="utf-8"))["project"]["version"]


def _read_inno_version(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
    if not match:
        raise ValueError(f"{path}: missing MyAppVersion")
    return match.group(1)


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    expected = {
        "dashboard/package.json": version,
        "backend/pyproject.toml": _pep440(version),
        "agent-windows/pyproject.toml": _pep440(version),
        "installer/child-device-windows/GuardianNodeChildSetup.iss": version,
        "installer/server-windows/GuardianNodeServerSetup.iss": version,
    }
    actual = {
        "dashboard/package.json": json.loads((ROOT / "dashboard/package.json").read_text(encoding="utf-8"))["version"],
        "backend/pyproject.toml": _read_toml_version("backend/pyproject.toml"),
        "agent-windows/pyproject.toml": _read_toml_version("agent-windows/pyproject.toml"),
        "installer/child-device-windows/GuardianNodeChildSetup.iss": _read_inno_version("installer/child-device-windows/GuardianNodeChildSetup.iss"),
        "installer/server-windows/GuardianNodeServerSetup.iss": _read_inno_version("installer/server-windows/GuardianNodeServerSetup.iss"),
    }
    failures = [
        f"{path}: expected {expected[path]}, got {actual[path]}"
        for path in expected
        if actual[path] != expected[path]
    ]
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
