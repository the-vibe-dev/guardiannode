from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHILD_INSTALLER = ROOT / "installer" / "child-device-windows" / "GuardianNodeChildSetup.iss"
SERVER_INSTALLER = ROOT / "installer" / "server-windows" / "GuardianNodeServerSetup.iss"
OLLAMA_BOOTSTRAP = ROOT / "installer" / "shared" / "configure_ollama_windows.ps1"
CLEAN_WINDOWS = ROOT / "installer" / "build" / "clean_windows_guardiannode.ps1"
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
    broker_install = _line_number(text, 'GuardianNodeBrokerService.exe"; Parameters: "install"')
    broker_start = _line_number(text, 'GuardianNodeBrokerService.exe"; Parameters: "start"')
    first_task_register = _line_number(text, 'Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\\register_agent_task.ps1')
    first_watchdog_start = _line_number(text, "GuardianNodeWatchdogService.exe\"; Parameters: \"start")

    assert config_line < first_backend_start
    assert config_line < broker_install
    assert broker_install < broker_start
    assert broker_start < first_task_register
    assert config_line < first_task_register
    assert config_line < first_watchdog_start
    assert "CurStepChanged" not in text


def test_server_installer_writes_config_before_backend_start() -> None:
    text = SERVER_INSTALLER.read_text(encoding="utf-8")

    config_line = _line_number(text, "BeforeInstall: WriteRuntimeConfigBeforeStart")
    backend_start = _line_number(text, "AfterInstall: RequireBackendHealth")

    assert config_line < backend_start
    assert "CurStepChanged" not in text


def test_server_installer_guides_private_lan_mode() -> None:
    text = SERVER_INSTALLER.read_text(encoding="utf-8")
    shared_env = (ROOT / "installer" / "shared" / "server_env_windows.iss").read_text(
        encoding="utf-8"
    )

    assert "Server access" in text
    assert "Private LAN/VPN child PCs can connect" in text
    assert "SERVERHOST" in text
    assert "ALLOWEDHOSTS" in text
    assert "ShouldEnableLanAccess" in text
    assert "GUARDIANNODE_BIND_HOST=0.0.0.0" not in shared_env
    assert "WriteGuardianNodeServerEnvForNetwork" in shared_env
    assert "'127.0.0.1,localhost,' + HostValue" in text
    assert "netsh.exe" in text
    assert "profile=private" in text
    assert "Check: ShouldEnableLanAccess" in text


def test_windows_installers_fail_if_ollama_bootstrap_fails() -> None:
    for path in (CHILD_INSTALLER, SERVER_INSTALLER):
        text = path.read_text(encoding="utf-8")
        assert "function PrepareToInstall(var NeedsRestart: Boolean): String;" in text
        assert "ExtractTemporaryFile('configure_ollama_windows.ps1')" in text
        assert "RunOllamaSetup(ExpandConstant('{tmp}\\configure_ollama_windows.ps1'))" in text
        assert "Result := 'GuardianNode Ollama/model setup failed." in text
        assert "BeforeInstall: RequireOllamaSetup" not in text

    child_text = CHILD_INSTALLER.read_text(encoding="utf-8")
    assert "if IsAllInOne then begin" in child_text
    assert "ModeParam := Lowercase(InstallerParam('MODE'))" in child_text
    assert "ModeParam = 'child'" in child_text
    assert "InstallerParam('SERVERURL') <> ''" in child_text
    assert "RunTesseractOnlySetup(ExpandConstant('{tmp}\\configure_ollama_windows.ps1'))" in child_text
    assert 'Result := \'GuardianNode OCR setup failed.' in child_text
    assert ' -Tier "text_only"' in child_text
    assert ' -TextModel ""' in child_text
    assert ' -TesseractOnly' in child_text
    assert 'Source: "..\\shared\\configure_ollama_windows.ps1"; Flags: dontcopy' in child_text

    server_text = SERVER_INSTALLER.read_text(encoding="utf-8")
    assert 'Source: "..\\shared\\configure_ollama_windows.ps1"; Flags: dontcopy' in server_text


def test_windows_ollama_bootstrap_registers_persistent_task() -> None:
    text = OLLAMA_BOOTSTRAP.read_text(encoding="utf-8")
    clean_text = CLEAN_WINDOWS.read_text(encoding="utf-8")
    server_text = SERVER_INSTALLER.read_text(encoding="utf-8")
    child_text = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert "GuardianNodeOllama" in text
    assert "Register-ScheduledTask" in text
    assert "ollama_serve_hidden.vbs" in text
    assert "[char]10" in text
    assert "[char]13" in text
    assert 'CreateObject("Scripting.FileSystemObject")' in text
    assert 'ExpandEnvironmentStrings("%LOCALAPPDATA%")' in text
    assert '[System.IO.File]::WriteAllText' in text
    assert '-Execute "wscript.exe"' in text
    assert 'cmd = Chr(34)' in text
    assert "shell.Run cmd, 0, True" in text
    assert "Start-ScheduledTask -TaskName \"GuardianNodeOllama\"" in text
    assert "New-ScheduledTaskTrigger -AtLogOn" in text
    assert "OLLAMA_MODELS" in text
    assert 'Join-Path $userProfile ".ollama\\models"' in text
    assert "return ,$names" in text
    assert "Ollama was not reachable after model setup" in text
    assert "Stop-OllamaProcesses -Reason \"post-pull reachability check\"" in text
    assert '"llama-server"' in clean_text

    assert "/Delete /TN GuardianNodeOllama /F" in server_text
    assert "/Delete /TN GuardianNodeOllama /F" in child_text


def test_windows_bootstrap_installs_tesseract_for_screenshot_text_detection() -> None:
    text = OLLAMA_BOOTSTRAP.read_text(encoding="utf-8")

    assert "Get-TesseractExecutable" in text
    assert "Install-Tesseract" in text
    assert "[switch]$TesseractOnly" in text
    assert "tesseract-ocr-w64-setup-5.5.0.20241111.exe" in text
    assert "Tesseract-OCR\\tesseract.exe" in text
    assert "'/S /D={0}'" in text
    assert "WaitForExit(600000)" in text
    assert "Tesseract installer timed out" in text
    assert "TESSDATA_PREFIX" in text
    assert 'SetEnvironmentVariable("Path"' in text
    assert "Tesseract-only mode requested. Skipping Ollama entirely." in text
    assert "screenshot text detection would be unreliable" in text
    assert text.index("Install-Tesseract") < text.index("Install-Ollama")


def test_child_only_install_does_not_stage_backend_or_dashboard_payload() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    backend_line = next(line for line in text.splitlines() if r"build\stage\backend\*" in line)

    assert "Check: IsAllInOne" in backend_line
    assert r"build\stage\dashboard\*" not in text
    assert r"UninstallDisplayIcon={app}\agent\{#MyAppExeName}" in text


def test_child_installer_does_not_collect_non_authoritative_age_group() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert "ChildProfilePage" not in text
    assert "AgeGroupValue" not in text
    assert "age_group:" not in text
    assert "How old is the child" not in text


def test_child_installer_uses_allow_only_service_dacl_and_no_taskbar_pin() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert "D;;" not in text
    assert "GuardianNodeServiceSddl" in text
    assert "sdset GuardianNodeBroker {#GuardianNodeServiceSddl}" in text
    assert "pin_to_taskbar" not in text


def test_child_installer_uses_single_watchdog_and_single_tray_launch_path() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")
    watchdog_xml = (ROOT / "installer" / "build" / "winsw_templates" / "Watchdog.xml").read_text(
        encoding="utf-8"
    )
    build_script = (ROOT / "installer" / "build" / "build_all.sh").read_text(encoding="utf-8")
    release_workflow = (ROOT / ".github" / "workflows" / "release-installers.yml").read_text(
        encoding="utf-8"
    )

    assert "GuardianNodeWatchdog2Service.exe\"; Parameters: \"install" not in text
    assert "GuardianNodeWatchdog2Service.exe\"; Parameters: \"start" not in text
    assert "sdset GuardianNodeWatchdog2" not in text
    assert "--peer-service" not in watchdog_xml
    assert "Helper.xml" not in build_script
    assert "Helper.xml" not in release_workflow
    assert 'GuardianNodeTray.exe"; Flags: nowait runasoriginaluser' not in text


def test_child_installer_installs_endpoint_broker_before_session_tasks() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")
    build_script = (ROOT / "installer" / "build" / "build_all.sh").read_text(encoding="utf-8")
    bundle_verify = (ROOT / "agent-windows" / "scripts" / "verify_windows_bundle.ps1").read_text(encoding="utf-8")

    assert "GuardianNodeBrokerService.exe" in text
    assert "GuardianNodeBrokerService.xml" in text
    assert "GuardianNodeBroker.exe\"; Parameters: \"--self-test" in text
    assert "GuardianNodeBroker.exe" in bundle_verify
    assert "Broker.xml" in build_script

    broker_start = _line_number(text, 'GuardianNodeBrokerService.exe"; Parameters: "start"')
    agent_task = _line_number(text, 'TaskName ""GuardianNodeAgent""')
    tray_task = _line_number(text, 'TaskName ""GuardianNodeTray""')
    watchdog_start = _line_number(text, 'GuardianNodeWatchdogService.exe"; Parameters: "start"')
    assert broker_start < agent_task
    assert broker_start < tray_task
    assert broker_start < watchdog_start

    assert "stop GuardianNodeBroker" in text
    assert 'GuardianNodeBrokerService.exe"; Parameters: "uninstall"' in text


def test_windows_repairs_preserve_state_and_restart_previous_release_on_failure() -> None:
    child = CHILD_INSTALLER.read_text(encoding="utf-8")
    server = SERVER_INSTALLER.read_text(encoding="utf-8")
    helper = (ROOT / "installer" / "shared" / "upgrade_helpers.iss").read_text(
        encoding="utf-8"
    )

    for text in (child, server):
        assert '#include "..\\shared\\upgrade_helpers.iss"' in text
        assert "GNCreatePreUpgradeBackup" in text
        assert "procedure DeinitializeSetup" in text
        assert "/api/health/ready" in text
        assert "ShouldInstallBackendService" in text

    assert "if IsExistingInstall then begin" in child
    existing_install_body = child.split("function IsExistingInstall: Boolean;", 1)[1].split(
        "end;", 1
    )[0]
    assert "ExpandConstant('{app}" not in existing_install_body
    assert "not FileExists(CfgPath)" in child
    assert "Secure\\device.json" in child
    assert "RestoreExistingServices" in child
    assert "if FileExists(AddBackslash(DataDir) + 'server.env') then" in server
    assert "start GuardianNodeBackend" in server
    assert "guardiannode.db-wal" in helper
    assert "keys" in helper


def test_child_installer_precreates_broker_secure_directories() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert r"GuardianNode\Secure" in text
    assert r"GuardianNode\AgentSecure" in text


def test_child_installer_hardens_broker_owned_data_before_start() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    config_line = _line_number(text, "BeforeInstall: WriteRuntimeConfigBeforeStart")
    harden_line = _line_number(text, "BeforeInstall: HardenDataAclsBeforeStart")
    broker_self_test = _line_number(text, 'GuardianNodeBroker.exe"; Parameters: "--self-test"')

    assert config_line < harden_line < broker_self_test
    assert '\\Secure" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F' in text
    assert '\\AgentSecure" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F' in text
    assert '\\keys" /inheritance:r /grant:r SYSTEM:(OI)(CI)F /grant:r Administrators:(OI)(CI)F' in text
    assert '\\server.env" /inheritance:r /grant:r SYSTEM:F /grant:r Administrators:F' in text


def test_child_installer_probe_uses_registry_vram_fallback_and_text_model_default() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert "HardwareInformation.qwMemorySize" in text
    assert "HardwareInformation.MemorySize" in text
    assert "DetectedTextModel := '{#GN_TEXT_ONLY_MODEL}'" in text
    assert "--query-gpu=memory.total" in text


def test_server_installer_probe_uses_registry_vram_fallback_when_nvml_fails() -> None:
    text = SERVER_INSTALLER.read_text(encoding="utf-8")

    assert "HardwareInformation.qwMemorySize" in text
    assert "HardwareInformation.MemorySize" in text
    assert "$smi.Source --query-gpu=memory.total" in text


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
