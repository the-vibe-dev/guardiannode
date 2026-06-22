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
