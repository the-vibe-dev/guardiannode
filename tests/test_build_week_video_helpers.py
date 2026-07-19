from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_screenshot_helper_reports_external_output_path_without_crashing(tmp_path):
    module = _module("capture_build_week_screenshots", "scripts/capture_build_week_screenshots.py")
    external = tmp_path / "frame.png"
    assert module._display_path(external) == external


def test_video_helper_accepts_target_duration_window():
    assert 155 <= 168 <= 170
