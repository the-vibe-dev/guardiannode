#!/usr/bin/env python3
"""Verify feature-matrix source and test references."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "FEATURE_MATRIX.md"
SENTINELS = {"Manual Windows validation", "Not implemented", "Not applicable"}


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
        if len(row) == 5:
            feature, legacy_status, _platform, source_module, test_reference = row
            if legacy_status == "Planned":
                continue
            code = "Present"
            coverage = "Manual" if test_reference in SENTINELS else "Unit"
            release = legacy_status
        elif len(row) == 8:
            feature, code, coverage, _qualification, _field, release, source_module, test_reference = row
        else:
            failures.append(f"Malformed row: {row!r}")
            continue
        if code == "Absent":
            if release != "Planned":
                failures.append(f"{feature}: absent code must be Planned, found {release!r}")
            continue
        if code != "Present":
            failures.append(f"{feature}: invalid code status {code!r}")
            continue
        if coverage == "None":
            failures.append(f"{feature}: present code cannot claim no automated coverage")
        for column, value in (("source module", source_module), ("test reference", test_reference)):
            ref = value.strip("`")
            if ref in SENTINELS:
                continue
            if ref.lower().startswith("planned "):
                failures.append(f"{feature}: invalid {column} sentinel {ref!r}")
                continue
            if not (ROOT / ref).exists():
                failures.append(f"{feature}: missing {column} {ref}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
