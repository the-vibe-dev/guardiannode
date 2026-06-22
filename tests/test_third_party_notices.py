from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_third_party_notices_match_direct_dependency_manifests() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_third_party_notices.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_stale_direct_dependency_claims_are_absent() -> None:
    text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").lower()

    assert "python-jose" not in text
    assert "tanstack" not in text
    assert "zod" not in text
