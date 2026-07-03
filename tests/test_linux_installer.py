from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "installer/server-linux/install.sh"


def _required_source_tree(root: Path) -> None:
    for path in (
        "backend/app",
        "installer/shared",
    ):
        (root / path).mkdir(parents=True, exist_ok=True)
    for path, content in {
        "LICENSE": "AGPL-3.0-only\n",
        "VERSION": "0.1.0-alpha.1\n",
        "backend/pyproject.toml": "[project]\nname = \"guardiannode-backend\"\n",
        "backend/app/main.py": "app = object()\n",
        "installer/shared/configure_ollama_linux.sh": "#!/usr/bin/env bash\n",
    }.items():
        (root / path).write_text(content, encoding="utf-8")


def _run_bash(script: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=REPO_ROOT,
        env={
            "GN_INSTALLER_LIBRARY_ONLY": "1",
            "GN_HOME": str(tmp_path / "gn-home"),
            "GN_DATA": str(tmp_path / "gn-data"),
            "GN_LOG": str(tmp_path / "gn-log"),
            "GN_USER": "nobody",
            "PATH": os.environ.get("PATH", ""),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_linux_installer_normalizes_github_style_archive_tree(tmp_path: Path) -> None:
    extracted = tmp_path / "extract"
    source_root = extracted / "guardiannode-main"
    target = tmp_path / "stage/src"
    _required_source_tree(source_root)

    result = _run_bash(
        f"""
        source {INSTALLER}
        normalize_extracted_source {extracted} {target}
        test -f {target}/backend/app/main.py
        test ! -d {target}/guardiannode-main
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_accepts_flat_archive_tree(tmp_path: Path) -> None:
    extracted = tmp_path / "extract"
    target = tmp_path / "stage/src"
    _required_source_tree(extracted)

    result = _run_bash(
        f"""
        source {INSTALLER}
        normalize_extracted_source {extracted} {target}
        test -f {target}/backend/app/main.py
        test -f {target}/LICENSE
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_rejects_archive_missing_backend(tmp_path: Path) -> None:
    extracted = tmp_path / "extract"
    target = tmp_path / "stage/src"
    extracted.mkdir(parents=True)
    (extracted / "LICENSE").write_text("AGPL-3.0-only\n", encoding="utf-8")

    result = _run_bash(
        f"""
        source {INSTALLER}
        normalize_extracted_source {extracted} {target}
        """,
        tmp_path,
    )

    assert result.returncode != 0
    assert "Source archive is missing required path: backend/pyproject.toml" in result.stderr


def test_linux_installer_create_user_prepares_writable_staging_dirs(tmp_path: Path) -> None:
    result = _run_bash(
        f"""
        source {INSTALLER}
        id() {{ return 0; }}
        chown() {{ :; }}
        chmod() {{ :; }}
        create_user
        test -d "$GN_HOME/staging"
        test -d "$GN_HOME/archived-src"
        test -d "$GN_HOME/archived-venv"
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_import_smoke_runs_from_staged_backend(tmp_path: Path) -> None:
    function_dump = tmp_path / "install_backend.fn"
    result = _run_bash(
        f"""
        source {INSTALLER}
        declare -f install_backend > "{function_dump}"
        grep -F 'cd "$GN_STAGED_SRC/backend"' "{function_dump}"
        grep -F 'importlib.import_module("app.main")' "{function_dump}"
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_setup_token_chowns_keys_dir(tmp_path: Path) -> None:
    calls = tmp_path / "chown.calls"
    result = _run_bash(
        f"""
        source {INSTALLER}
        chown() {{ printf '%s\\n' "$*" >> "{calls}"; }}
        chmod() {{ :; }}
        create_setup_token
        test -d "$GN_DATA/keys"
        test -f "$GN_DATA/keys/setup_token.json"
        grep -F "$GN_USER:$GN_USER $GN_DATA/keys" "{calls}"
        grep -F "$GN_USER:$GN_USER $GN_DATA/keys/setup_token.json" "{calls}"
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_rollback_stops_service_before_moving_paths(tmp_path: Path) -> None:
    function_dump = tmp_path / "rollback_release.fn"
    result = _run_bash(
        f"""
        source {INSTALLER}
        declare -f rollback_release > "{function_dump}"
        grep -F 'systemctl stop guardiannode-backend.service' "{function_dump}"
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_probe_failure_defaults_conservatively(tmp_path: Path) -> None:
    result = _run_bash(
        f"""
        source {INSTALLER}
        sudo() {{ return 1; }}
        probe_hardware_and_pick_tier
        test "$GN_TIER" = "text_only"
        test "${{GN_TEXT_MODEL-unset}}" = ""
        test "${{GN_VISION_MODEL-unset}}" = ""
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_systemd_preserves_blank_model_values(tmp_path: Path) -> None:
    unit_path = tmp_path / "guardiannode-backend.service"
    result = _run_bash(
        f"""
        source {INSTALLER}
        systemctl() {{ :; }}
        GN_TIER="text_only"
        GN_TEXT_MODEL=""
        GN_VISION_MODEL=""
        GN_SYSTEMD_UNIT_PATH="{unit_path}"
        write_systemd_unit
        grep -F 'Environment="GUARDIANNODE_CLASSIFIER_TIER=text_only"' "{unit_path}"
        grep -F 'Environment="GUARDIANNODE_TEXT_MODEL="' "{unit_path}"
        grep -F 'Environment="GUARDIANNODE_VISION_MODEL="' "{unit_path}"
        ! grep -F 'llama3.2:3b' "{unit_path}"
        ! grep -F 'qwen3-vl:8b-instruct' "{unit_path}"
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_linux_installer_probe_values_render_verbatim(tmp_path: Path) -> None:
    unit_path = tmp_path / "guardiannode-backend.service"
    result = _run_bash(
        f"""
        source {INSTALLER}
        systemctl() {{ :; }}
        GN_TIER="full"
        GN_TEXT_MODEL="llama3.2:1b"
        GN_VISION_MODEL="qwen3-vl:8b-instruct"
        GN_SYSTEMD_UNIT_PATH="{unit_path}"
        write_systemd_unit
        grep -F 'Environment="GUARDIANNODE_CLASSIFIER_TIER=full"' "{unit_path}"
        grep -F 'Environment="GUARDIANNODE_TEXT_MODEL=llama3.2:1b"' "{unit_path}"
        grep -F 'Environment="GUARDIANNODE_VISION_MODEL=qwen3-vl:8b-instruct"' "{unit_path}"
        """,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr + result.stdout
