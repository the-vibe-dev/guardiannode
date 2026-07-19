#!/usr/bin/env python3
"""Check the final MP4 duration and report a SHA-256 digest.

Requires ffprobe on PATH. The command is read-only and does not upload or edit
the video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    args = parser.parse_args()
    path = args.video.resolve()
    if not path.is_file() or path.suffix.lower() != ".mp4":
        raise SystemExit("Expected an existing MP4 file")
    duration = _duration(path)
    result = {
        "file": path.name,
        "duration_seconds": round(duration, 3),
        "duration_gate": "passed" if 155 <= duration <= 170 else "failed",
        "sha256": _sha256(path),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["duration_gate"] == "passed" else 1)


if __name__ == "__main__":
    main()
