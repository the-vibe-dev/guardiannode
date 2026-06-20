#!/usr/bin/env python3
"""Verify that implemented/experimental feature-matrix source paths exist."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "FEATURE_MATRIX.md"
CHECKED_STATUSES = {"Implemented", "Experimental"}


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", ":"}:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0] != "Feature":
            rows.append(cells)
    return rows


def main() -> int:
    failures: list[str] = []
    for row in _table_rows(MATRIX.read_text(encoding="utf-8")):
        if len(row) < 5:
            failures.append(f"Malformed row: {row!r}")
            continue
        feature, status, _platform, source_module, _test = row[:5]
        if status not in CHECKED_STATUSES:
            continue
        source = source_module.strip("`")
        if source in {"Manual Windows validation", "Not implemented"}:
            continue
        if not (ROOT / source).exists():
            failures.append(f"{feature}: missing source module {source}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
