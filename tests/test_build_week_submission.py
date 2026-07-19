from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts" / "check_build_week_submission.py"
    spec = importlib.util.spec_from_file_location("check_build_week_submission", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_week_submission_package_is_complete():
    result = _module().validate()
    assert result["status"] == "passed", result["failures"]


def test_caption_runtime_is_under_three_minutes():
    module = _module()
    runtime = module._last_caption_seconds(
        ROOT / "docs" / "build-week" / "video" / "CAPTIONS.srt"
    )
    assert 155 <= runtime <= 170
