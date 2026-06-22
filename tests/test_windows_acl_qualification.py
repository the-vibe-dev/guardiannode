from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "child-device-windows" / "qualify_acls.ps1"
CHILD_INSTALLER = ROOT / "installer" / "child-device-windows" / "GuardianNodeChildSetup.iss"


def test_acl_qualification_script_checks_broker_owned_sensitive_state() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    for required in (
        "GuardianNodeBroker",
        "Secure\\device.json",
        "Secure\\parent.json",
        "Secure\\pause_state.json",
        "AgentSecure\\queue.sqlite",
        "AgentSecure\\queue.key",
        "keys\\device_bootstrap_token.json",
        "keys\\master.key.dpapi",
        "server.env",
    ):
        assert required in text

    assert "S-1-5-32-545" in text  # Builtin Users
    assert "S-1-1-0" in text  # Everyone
    assert "S-1-5-18" in text  # LocalSystem
    assert "S-1-5-32-544" in text  # Builtin Administrators
    assert "FileSystemRights]::FullControl" in text
    assert "throw" in text


def test_acl_qualification_collects_reproducible_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "icacls.exe" in text
    assert "Get-Acl" in text
    assert "sc.exe sdshow" in text
    assert "schtasks.exe /Query" in text
    assert "service-sddl.json" in text
    assert "get-acl-protected.json" in text
    assert "icacls-guardiannode.txt" in text


def test_child_installer_stages_acl_qualification_script() -> None:
    text = CHILD_INSTALLER.read_text(encoding="utf-8")

    assert 'Source: "qualify_acls.ps1"; DestDir: "{app}"' in text
