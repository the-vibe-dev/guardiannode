from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / "agent-windows"


def test_documented_agent_cli_smoke_options_work() -> None:
    for arg in ("--help", "--version"):
        result = subprocess.run(
            [sys.executable, "-m", "src.main", arg],
            cwd=AGENT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_readme_does_not_reference_removed_once_flag() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    removed_flag = "--" + "once"

    assert removed_flag not in readme
