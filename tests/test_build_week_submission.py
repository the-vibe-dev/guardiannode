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


def test_source_archive_checks_links_without_git_or_generated_dependencies(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "README.md").write_text("[Missing](missing.md)", encoding="utf-8")
    dependencies = tmp_path / "node_modules"
    dependencies.mkdir()
    (dependencies / "dependency.md").write_text("ignored", encoding="utf-8")
    paths = module._tracked_markdown()
    assert paths == [tmp_path / "README.md"]
    assert module._check_local_links(paths) == ["README.md -> missing.md"]


def test_source_archive_does_not_claim_baseline_tag_verification():
    module = _module()
    if not (ROOT / ".git").exists():
        result = module.validate()
        assert result["baseline_verification"] == "unavailable_source_archive"
        assert any("provenance was not verified" in item for item in result["manual_gates"])
