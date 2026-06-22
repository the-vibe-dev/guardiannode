from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHILD_INSTALLER = ROOT / "installer" / "child-device-windows" / "GuardianNodeChildSetup.iss"
SERVER_INSTALLER = ROOT / "installer" / "server-windows" / "GuardianNodeServerSetup.iss"
WATCHDOG = ROOT / "agent-windows" / "src" / "watchdog.py"


def _line_number(text: str, needle: str) -> int:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    raise AssertionError(f"missing installer line containing {needle!r}")


def test_child_installer_writes_config_before_starting_components() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    config_line = _line_number(text, "BeforeInstall: WriteRuntimeConfigBeforeStart")
    first_backend_start = _line_number(text, 'Parameters: "start"; Flags: runhidden waituntilterminated; Check: IsAllInOne')
    first_task_register = _line_number(text, 'Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\\register_agent_task.ps1')
    first_watchdog_start = _line_number(text, "GuardianNodeWatchdogService.exe\"; Parameters: \"start")

    assert config_line < first_backend_start
    assert config_line < first_task_register
    assert config_line < first_watchdog_start
    assert "CurStepChanged" not in text


def test_server_installer_writes_config_before_backend_start() -> None:
    text = SERVER_INSTALLER.read_text(encoding="utf-8")

    config_line = _line_number(text, "BeforeInstall: WriteRuntimeConfigBeforeStart")
    backend_start = _line_number(text, "AfterInstall: RequireBackendHealth")

    assert config_line < backend_start
    assert "CurStepChanged" not in text


def test_child_only_install_does_not_stage_backend_or_dashboard_payload() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    backend_line = next(line for line in text.splitlines() if r"build\stage\backend\*" in line)
    dashboard_line = next(line for line in text.splitlines() if r"build\stage\dashboard\*" in line)

    assert "Check: IsAllInOne" in backend_line
    assert "Check: IsAllInOne" in dashboard_line
    assert r"UninstallDisplayIcon={app}\agent\{#MyAppExeName}" in text


def test_child_installer_uses_allow_only_service_dacl_and_no_taskbar_pin() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert "D;;" not in text
    assert "GuardianNodeServiceSddl" in text
    assert "pin_to_taskbar" not in text


def test_watchdog_respects_installer_maintenance_marker() -> None:
    text = WATCHDOG.read_text(encoding="utf-8")

    assert "maintenance.flag" in text
    assert "_maintenance_mode_active" in text
    assert "watchdog repair actions paused" in text


def test_windows_installers_use_generated_hardware_tier_constants() -> None:
    for path in (CHILD_INSTALLER, SERVER_INSTALLER):
        text = path.read_text(encoding="utf-8")
        assert '#include "..\\shared\\hardware_tiers.iss"' in text
        assert "{#GN_FULL_MIN_VRAM_GB}" in text
        assert "{#GN_VISION_ONLY_MIN_VRAM_GB}" in text
        assert "{#GN_VISION_MODEL}" in text
        assert "VramGB >= 10" not in text
        assert "VramGB >= 6" not in text
