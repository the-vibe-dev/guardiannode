"""Filesystem helpers for encrypted evidence blobs."""
from __future__ import annotations

import re
from pathlib import Path

from app import settings as settings_mod

_BLOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class UnsafeEvidencePathError(ValueError):
    """Raised when a stored evidence path escapes the evidence directory."""


def evidence_root() -> Path:
    root = settings_mod.settings.evidence_dir
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def evidence_blob_path(blob_id: str) -> Path:
    if not _BLOB_ID_RE.fullmatch(blob_id):
        raise UnsafeEvidencePathError("invalid evidence blob id")
    return evidence_root() / blob_id[:2] / f"{blob_id}.enc"


def resolve_stored_evidence_path(stored_path: str | Path, *, must_exist: bool = True) -> Path:
    """Resolve a DB evidence path and require it to stay under evidence_root()."""
    if not str(stored_path):
        raise UnsafeEvidencePathError("empty evidence path")

    root = evidence_root()
    raw = Path(stored_path)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise UnsafeEvidencePathError("evidence path escapes evidence directory")

    if candidate.is_relative_to(root):
        for probe in (candidate, *candidate.parents):
            if probe == root.parent:
                break
            if probe.is_symlink():
                raise UnsafeEvidencePathError("evidence path uses a symlink")
            if probe == root:
                break

    if must_exist and not resolved.is_file():
        raise FileNotFoundError(str(stored_path))
    return resolved
