"""Watchdog process (runs as a SYSTEM service).

The agent itself runs per user session via the `GuardianNodeAgent` scheduled
task (Windows services live in session 0 and cannot capture a user's desktop).
The watchdog's job is tamper resistance: if the agent process disappears from
every session — e.g. the child kills it from Task Manager — re-run the
scheduled task, which starts it back up in the logged-on user's session.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import time

log = logging.getLogger("guardiannode.watchdog")

AGENT_PROCESS_NAME = "GuardianNodeAgent.exe"
AGENT_TASK_NAME = "GuardianNodeAgent"


def _agent_process_running_windows() -> bool:
    """True if the agent process exists in any session (SYSTEM sees them all)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {AGENT_PROCESS_NAME}", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        return AGENT_PROCESS_NAME.lower() in (out.stdout or "").lower()
    except Exception:
        return False


def _agent_task_start_windows() -> bool:
    """Re-run the logon task. Task Scheduler starts interactive group tasks in
    the logged-on user's session; fails harmlessly when no one is signed in."""
    try:
        r = subprocess.run(
            ["schtasks", "/Run", "/TN", AGENT_TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _service_running_systemd(unit: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=5)
        return (r.stdout or "").strip() == "active"
    except Exception:
        return False


def watchdog_loop(interval: int = 5) -> None:
    log.info("watchdog started for %s every %ds", AGENT_TASK_NAME, interval)
    failures = 0
    while True:
        running = False
        if os.name == "nt":
            running = _agent_process_running_windows()
            if not running:
                log.warning("agent process not found in any session; re-running scheduled task")
                _agent_task_start_windows()
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
