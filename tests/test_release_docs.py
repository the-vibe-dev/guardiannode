from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_source_quick_start_documents_setup_token() -> None:
    combined = read("README.md") + "\n" + read("docs/index.md")

    assert "setup_token.json" in combined
    assert "http://127.0.0.1:8787/setup" in combined
    assert "Do not post the setup token" in combined


def test_unsupported_agent_once_flag_is_not_documented() -> None:
    combined = (
        read("README.md")
        + "\n"
        + read("docs/index.md")
        + "\n"
        + read("docs/AGENT_WINDOWS.md")
    )

    assert "--once" not in combined


def test_key_management_docs_do_not_use_stale_dpapi_claim() -> None:
    combined = (
        read("README.md")
        + "\n"
        + read("PRIVACY.md")
        + "\n"
        + read("SECURITY.md")
        + "\n"
        + read("docs/BACKEND_SETUP.md")
        + "\n"
        + read("docs/THREAT_MODEL.md")
    )

    assert "It is not currently wrapped by DPAPI" not in combined
    assert "keys/master.key.dpapi" in combined
    assert "export-key-backup" in combined
    assert "import-key-backup" in combined
    assert "The 12-word recovery code resets the parent dashboard account only" in combined


def test_privacy_states_plaintext_metadata_and_disk_encryption_boundary() -> None:
    privacy = read("PRIVACY.md")

    assert "plaintext metadata" in privacy
    assert "full-disk encryption" in privacy
    assert "GuardianNode does not encrypt the whole SQLite database" in privacy


def test_export_manifest_does_not_hard_code_raw_master_key_only() -> None:
    storage_api = read("backend/app/api/storage.py")

    assert "keys/master.key) with the blob_id" not in storage_api
    assert "DPAPI-wrapped on Windows" in storage_api
    assert "portable key backup" in storage_api


def test_alpha_release_docs_match_public_installer_scope() -> None:
    combined = (
        read("README.md")
        + "\n"
        + read("docs/index.md")
        + "\n"
        + read("docs/RELEASE_NOTES_0.1.0-alpha.1.md")
        + "\n"
        + read("docs/release/windows-11-alpha-installer-validation.md")
    )

    assert "technical parents" in combined
    assert "GuardianNodeChildSetup-0.1.0-alpha.1.exe" in combined
    assert "GuardianNodeServerSetup-0.1.0-alpha.1.exe" in combined
    assert "b271dd24c448ac8c333f5c86548cac2d12c35a41c48de7193d62f376becb1fb7" in combined
    assert "92314f7613341bd2ba47c34d96131f44e63126ef7cacd248f59642604fcf954f" in combined
    assert "Do not expose GuardianNode directly to the public internet" in combined
    normalized = " ".join(combined.split())
    assert "not a guarantee of child safety" in normalized
    assert "not a replacement for parental involvement" in normalized
    assert "Public Windows installer | Not supported" not in combined
    assert "Windows installers are intentionally not attached" not in combined


def test_public_installer_docs_do_not_contradict_alpha_scope() -> None:
    combined = (
        read("README.md")
        + "\n"
        + read("docs/ROADMAP.md")
        + "\n"
        + read("docs/INSTALLER_ARCHITECTURE.md")
        + "\n"
        + read("docs/DEVICE_PAIRING.md")
    )

    forbidden = [
        "installer paths are for maintainer qualification only",
        "not the supported public installation method",
        "maintainer qualification only",
        "installer no-go",
        "before public installer distribution",
        "public Windows installers are not supported",
        "Windows installers are intentionally not attached",
        "Source-only GitHub release workflow",
    ]

    lowered = combined.lower()
    for phrase in forbidden:
        assert phrase.lower() not in lowered

    assert "Windows 11 all-in-one installer is a supported public-alpha path" in combined
    assert "Windows server installer" in combined
    assert "Windows child-device/all-in-one installer" in combined
    assert "public alpha installer artifacts" in combined
