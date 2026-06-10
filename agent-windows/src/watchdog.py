"""Watchdog process.

Polls the agent's heartbeat. If the agent service is not running, restarts it
via the Service Control Manager (Windows) or systemctl (Linux dev).
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger("guardiannode.watchdog")

AGENT_SERVICE_NAME = "GuardianNodeAgent"


def _service_running_windows(name: str) -> bool:
    try:
        out = subprocess.run(["sc", "query", name], capture_output=True, text=True, timeout=5)
        return "RUNNING" in (out.stdout or "")
    except Exception:
        return False


def _service_start_windows(name: str) -> bool:
    try:
        r = subprocess.run(["sc", "start", name], capture_output=True, text=True, timeout=10)
        return r.returncode in (0, 1056)  # 1056 = already running
    except Exception:
        return False


def _service_running_systemd(unit: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=5)
        return (r.stdout or "").strip() == "active"
    except Exception:
        return False


def watchdog_loop(interval: int = 5) -> None:
    log.info("watchdog started for %s every %ds", AGENT_SERVICE_NAME, interval)
    failures = 0
    while True:
        running = False
        if os.name == "nt":
            running = _service_running_windows(AGENT_SERVICE_NAME)
            if not running:
                log.warning("agent service not running; attempting restart")
                _service_start_windows(AGENT_SERVICE_NAME)
        else:
            unit = "guardiannode-agent.service"
            running = _service_running_systemd(unit)
            if not running:
                log.info("(dev) agent unit not active: %s", unit)

        if not running:
            failures += 1
        else:
            failures = 0

        if failures > 10:
            log.error("agent has not come back after %d attempts; backing off", failures)
            time.sleep(60)
            failures = 0
        time.sleep(interval)


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode watchdog")
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    watchdog_loop(args.interval)


if __name__ == "__main__":  # pragma: no cover
    cli()
