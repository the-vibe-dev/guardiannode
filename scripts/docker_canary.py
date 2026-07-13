#!/usr/bin/env python3
"""Build a clean Compose stack and prove screenshot OCR reaches an alert."""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "installer" / "server-linux" / "docker-compose.yml"
CANARY_COMPOSE_FILE = ROOT / "installer" / "server-linux" / "docker-compose.canary.yml"
PROJECT = os.environ.get("GUARDIANNODE_CANARY_PROJECT", "guardiannode-canary")
BASE_URL = os.environ.get("GUARDIANNODE_CANARY_URL", "http://127.0.0.1:18787")
PHRASE = "GUARDIAN ORCHID SEVEN CANARY"


def compose(*args: str, capture: bool = False) -> str:
    command = [
        "docker", "compose", "-p", PROJECT,
        "-f", str(COMPOSE_FILE), "-f", str(CANARY_COMPOSE_FILE), *args,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return (result.stdout or "").strip()


def container_token(expression: str) -> str:
    return compose(
        "exec", "-T", "backend", "env", "PYTHONPATH=/app/backend", "python", "-c", expression,
        capture=True,
    ).splitlines()[-1]


def canary_png() -> bytes:
    image = Image.new("RGB", (1400, 420), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 72)
    except OSError:
        font = ImageFont.load_default()
    draw.text((70, 150), PHRASE, fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def wait_ready(client: httpx.Client, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/health/ready")
            last = response.text
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise RuntimeError(f"backend did not become ready: {last}")


def expect(response: httpx.Response, status: int = 200) -> dict:
    if response.status_code != status:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.status_code} {response.text}")
    return response.json()


def run_canary() -> None:
    environment = os.environ.copy()
    environment["GUARDIANNODE_CLASSIFIER_MODE"] = "rules_only"
    environment["GUARDIANNODE_HOST_PORT"] = "18787"
    os.environ.update(environment)
    compose("down", "-v", "--remove-orphans")
    compose("up", "--build", "-d")

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        wait_ready(client)
        setup_token = container_token(
            "from app.services.setup_token import ensure_setup_token; print(ensure_setup_token())"
        )
        expect(client.post("/api/auth/setup", json={
            "display_name": "Canary Parent",
            "password": "canary-password-not-production",
            "recovery_code": "canary recovery code",
            "setup_token": setup_token,
        }))
        csrf = expect(client.get("/api/auth/csrf"))["csrf_token"]
        browser_headers = {"x-csrf-token": csrf}
        profile = expect(client.post("/api/profiles", headers=browser_headers, json={
            "display_name": "Canary Child",
            "age_group": "10_13",
            "custom_watch_phrases": [PHRASE],
        }))
        pair = expect(client.post("/api/devices/pair/start", headers=browser_headers, json={}))
        device = expect(client.post("/api/devices/pair/complete", json={
            "code": pair["code"], "hostname": "canary-device", "platform": "linux-canary",
        }))
        expect(client.patch(
            f"/api/devices/{device['device_id']}/profile",
            headers=browser_headers,
            json={"profile_id": profile["profile_id"]},
        ))
        upload = expect(client.post(
            "/api/events/screenshot",
            headers={"authorization": f"Bearer {device['device_token']}"},
            files={"image": ("canary.png", canary_png(), "image/png")},
            data={"capture_scope": "visible_desktop", "idempotency_key": "docker-canary-v1"},
        ))
        if not upload.get("queued"):
            raise RuntimeError(f"screenshot was accepted without queueing: {upload}")

        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            alerts = expect(client.get("/api/alerts"))
            if alerts:
                detail = expect(client.get(f"/api/alerts/{alerts[0]['alert_id']}"))
                if PHRASE not in (detail.get("redacted_text") or ""):
                    raise RuntimeError("alert exists but OCR did not extract the canary phrase")
                if "custom_watch" not in detail["risk"]["categories"]:
                    raise RuntimeError("alert exists but expected custom_watch classification is absent")
                print(f"Docker canary passed: alert={alerts[0]['alert_id']} phrase={PHRASE}")
                return
            time.sleep(2)
        raise RuntimeError("screenshot was accepted but no alert was created")


def main() -> int:
    try:
        run_canary()
        return 0
    except (RuntimeError, subprocess.CalledProcessError, httpx.HTTPError) as exc:
        print(f"Docker canary failed: {exc}", file=sys.stderr)
        try:
            compose("ps")
            compose("logs", "--no-color", "--tail", "200")
        except subprocess.CalledProcessError:
            pass
        return 1
    finally:
        try:
            compose("down", "-v", "--remove-orphans")
        except subprocess.CalledProcessError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
