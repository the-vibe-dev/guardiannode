from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import check_feature_matrix


def _write_matrix(path: Path, rows: list[str]) -> None:
    path.write_text(
        "\n".join(
            [
                "| Feature | Status | Platform | Source module | Test reference |",
                "|---|---|---|---|---|",
                *rows,
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_feature_matrix_valid_source_and_test_paths_pass(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    test = tmp_path / "test_source.py"
    source.write_text("", encoding="utf-8")
    test.write_text("", encoding="utf-8")
    matrix = tmp_path / "FEATURE_MATRIX.md"
    _write_matrix(matrix, ["| Example | Implemented | Backend | `source.py` | `test_source.py` |"])
    monkeypatch.setattr(check_feature_matrix, "ROOT", tmp_path)
    monkeypatch.setattr(check_feature_matrix, "MATRIX", matrix)

    assert check_feature_matrix.main() == 0


def test_feature_matrix_missing_source_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    test = tmp_path / "test_source.py"
    test.write_text("", encoding="utf-8")
    matrix = tmp_path / "FEATURE_MATRIX.md"
    _write_matrix(matrix, ["| Example | Implemented | Backend | `missing.py` | `test_source.py` |"])
    monkeypatch.setattr(check_feature_matrix, "ROOT", tmp_path)
    monkeypatch.setattr(check_feature_matrix, "MATRIX", matrix)

    assert check_feature_matrix.main() == 1
    assert "Example: missing source module missing.py" in capsys.readouterr().err


def test_feature_matrix_missing_test_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.py"
    source.write_text("", encoding="utf-8")
    matrix = tmp_path / "FEATURE_MATRIX.md"
    _write_matrix(matrix, ["| Example | Experimental | Backend | `source.py` | `missing_test.py` |"])
    monkeypatch.setattr(check_feature_matrix, "ROOT", tmp_path)
    monkeypatch.setattr(check_feature_matrix, "MATRIX", matrix)

    assert check_feature_matrix.main() == 1
    assert "Example: missing test reference missing_test.py" in capsys.readouterr().err


def test_feature_matrix_sentinels_pass(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("", encoding="utf-8")
    matrix = tmp_path / "FEATURE_MATRIX.md"
    _write_matrix(
        matrix,
        [
            "| Windows tray | Experimental | Windows | `source.py` | Manual Windows validation |",
            "| Planned broker | Planned | Windows | Planned broker service | Not implemented |",
        ],
    )
    monkeypatch.setattr(check_feature_matrix, "ROOT", tmp_path)
    monkeypatch.setattr(check_feature_matrix, "MATRIX", matrix)

    assert check_feature_matrix.main() == 0
