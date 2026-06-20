from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHILD_INSTALLER = ROOT / "installer" / "child-device-windows" / "GuardianNodeChildSetup.iss"
POWER_INSTALL = ROOT / "docs" / "POWER_USER_INSTALL.md"


def test_child_installer_validates_silent_inputs_before_cleanup() -> None:
    source = CHILD_INSTALLER.read_text(encoding="utf-8")

    prepare_pos = source.index("function PrepareToInstall")
    validate_pos = source.index("if not ValidateInstallInputs(ErrorMessage)", prepare_pos)
    cleanup_pos = source.index("RunHidden('{sys}\\sc.exe'", prepare_pos)

    assert validate_pos < cleanup_pos
    assert "Skip validation entirely in silent" not in source
    assert "if WizardSilent() then Exit;" in source
    assert "function ValidateInstallInputs" in source
    assert "Silent install requires /MODE=allinone or /MODE=child." in source
    assert "Invalid /MODE. Use /MODE=allinone or /MODE=child." in source
    assert "Use GuardianNodeServerSetup for /MODE=server installs." in source


def test_child_installer_uses_strict_url_code_and_json_contracts() -> None:
    source = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert "function IsValidServerUrl" in source
    assert "ContainsAny(Url" in source
    assert "Pos('@', Url)" in source
    assert "Pos('#', Url)" in source
    assert "Pos('?', Url)" in source
    assert "Copy(Lowercase(Url), 1, 7) = 'http://'" in source
    assert "Copy(Lowercase(Url), 1, 8) = 'https://'" in source
    assert "function HasOnlyAsciiDigits" in source
    assert "HasOnlyAsciiDigits(PairCode, 6)" in source
    assert "JsonEscape(ServerUrl)" in source
    assert "JsonEscape(Trim(ServerConnectionPage.Values[1]))" in source
    assert "Pos('http', url)" not in source
    assert "Length(Trim(ServerConnectionPage.Values[1])) <> 6" not in source


def test_power_user_docs_use_current_silent_mode_contract() -> None:
    docs = POWER_INSTALL.read_text(encoding="utf-8")

    assert "/MODE=child" in docs
    assert "/MODE=allinone" in docs
    assert "/MODE=separated" not in docs
    assert "six-digit pairing code" in docs
