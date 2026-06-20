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
