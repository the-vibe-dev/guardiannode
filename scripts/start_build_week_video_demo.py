#!/usr/bin/env python3
"""Start a disposable, mock-only GuardianNode instance for video recording.

The helper never reads an existing GuardianNode data directory and never loads
an OpenAI key. Complete first-run setup off camera, then record only the
synthetic dashboard flow. Stop with Ctrl+C; disposable data is removed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def _wait_for(url: str, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"Disposable video backend did not start at {url}")


def _environment(data_dir: Path, port: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GUARDIANNODE_DATA_DIR": str(data_dir),
            "GUARDIANNODE_BIND_HOST": "127.0.0.1",
            "GUARDIANNODE_PORT": str(port),
            "GUARDIANNODE_GUARDIAN_REVIEW_ENABLED": "true",
            "GUARDIANNODE_GUARDIAN_REVIEW_PROVIDER": "mock",
            "GUARDIANNODE_DEMO_MODE_ENABLED": "true",
            "GUARDIANNODE_MDNS_ENABLED": "false",
            "GUARDIANNODE_RETENTION_CLEANUP_ENABLED": "false",
            "GUARDIANNODE_DEVICE_OFFLINE_ALERT_ENABLED": "false",
            "GUARDIANNODE_NOTIFICATION_WORKER_ENABLED": "false",
            "GUARDIANNODE_DATABASE_BACKUP_ENABLED": "false",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    env.pop("GUARDIANNODE_OPENAI_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    return env


def _serve(data_dir: Path, port: int, open_browser: bool) -> None:
    base_url = f"http://127.0.0.1:{port}"
    log_path = data_dir / "video-demo-backend.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=BACKEND,
            env=_environment(data_dir, port),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for(f"{base_url}/api/health")
            setup_path = data_dir / "keys" / "setup_token.json"
            deadline = time.monotonic() + 10
            while not setup_path.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            if not setup_path.exists():
                raise RuntimeError("first-run setup token file was not created")
            print(
                json.dumps(
                    {
                        "status": "ready",
                        "url": base_url,
                        "setup_url": f"{base_url}/setup",
                        "setup_token_file": str(setup_path),
                        "provider": "mock",
                        "synthetic_only": True,
                        "api_key_loaded": False,
                        "instructions": (
                            "Complete setup off camera, open Synthetic demo, and use only "
                            "the manufactured scenarios. Press Ctrl+C here when finished."
                        ),
                    },
                    indent=2,
                ),
                flush=True,
            )
            if open_browser:
                webbrowser.open(f"{base_url}/setup")
            while process.poll() is None:
                time.sleep(0.5)
            raise RuntimeError(f"video backend exited unexpectedly with code {process.returncode}")
        except KeyboardInterrupt:
            print("Stopping disposable video backend.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8879)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="optional disposable data path; must not point at a real GuardianNode directory",
    )
    args = parser.parse_args()
    if args.data_dir:
        data_dir = args.data_dir.resolve()
        if data_dir.exists() and any(data_dir.iterdir()):
            raise SystemExit("Refusing to use a non-empty video demo data directory")
        data_dir.mkdir(parents=True, exist_ok=True)
        _serve(data_dir, args.port, args.open_browser)
    else:
        with tempfile.TemporaryDirectory(prefix="guardiannode-video-demo-") as temp:
            _serve(Path(temp), args.port, args.open_browser)


if __name__ == "__main__":
    main()
