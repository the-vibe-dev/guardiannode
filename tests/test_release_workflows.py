from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLERS = ROOT / ".github" / "workflows" / "release-installers.yml"
SOURCE_RELEASE = ROOT / ".github" / "workflows" / "source-release.yml"
TESTS = ROOT / ".github" / "workflows" / "test.yml"


def test_installer_release_does_not_run_on_ordinary_source_tags() -> None:
    text = INSTALLERS.read_text(encoding="utf-8")

    assert '"v*-installer-test*"' in text
    assert '"v*"' not in text
    assert "workflow_dispatch:" in text


def test_source_release_is_prerelease_and_rejects_windows_binaries() -> None:
    text = SOURCE_RELEASE.read_text(encoding="utf-8")

    assert '"v*"' in text
    assert "!contains(github.ref_name, '-installer-test')" in text
    assert "prerelease: true" in text
    assert "body_path: docs/RELEASE_NOTES_0.1.0-alpha.1.md" in text
    assert "-iname '*.exe'" in text
    assert "-iname '*.msi'" in text
    assert "installer/build/dist/*.exe" not in text
    assert "diff -qr dist ../backend/app/static" in text
    assert "pip-audit --strict ." in text


def test_ci_checks_generated_hardware_tier_constants() -> None:
    text = TESTS.read_text(encoding="utf-8")

    assert "python scripts/sync_hardware_tiers.py --check" in text
    assert "python scripts/check_third_party_notices.py" in text
