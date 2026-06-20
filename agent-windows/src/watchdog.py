"""Watchdog process (runs as a SYSTEM service).

The agent and tray run per user session via scheduled tasks (Windows services
live in session 0 and cannot touch a user's desktop). This watchdog provides
tamper resistance: if either disappears — e.g. the child ends them from Task
Manager — it re-runs their scheduled tasks, which relaunch them in the
logged-on user's session.

Two copies of this watchdog run as services under different names
(`GuardianNodeWatchdog` and an obscurely-named peer). Each is told its peer via
``--peer-service`` and restarts the peer if it is stopped, so ending one
service from Task Manager is undone by the other. A child who is a local
admin can still kill everything at once, which is why the backend also raises
an alert when a device stops sending heartbeats — see the offline monitor.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import time

log = logging.getLogger("guardiannode.watchdog")

# (process image, scheduled-task name) pairs the watchdog keeps alive.
WATCHED = [
    ("GuardianNodeAgent.exe", "GuardianNodeAgent"),
    ("GuardianNodeTray.exe", "GuardianNodeTray"),
]


def _process_running_windows(image: str) -> bool:
    """True if the process exists in any session (SYSTEM sees them all)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        return image.lower() in (out.stdout or "").lower()
    except Exception:
        return False


def _any_user_logged_in() -> bool:
    """The tray only exists when someone is signed in; don't fight an empty
    session by spamming schtasks for it."""
    try:
        out = subprocess.run(["quser"], capture_output=True, text=True, timeout=10)
        return bool((out.stdout or "").strip()) and "No User exists" not in (out.stderr or "")
    except Exception:
        # quser is absent on some SKUs; assume someone may be logged in.
        return True


def _task_run_windows(task_name: str) -> bool:
    """Re-run a logon task. Task Scheduler launches interactive group tasks in
    the logged-on user's session; fails harmlessly when no one is signed in."""
    try:
        r = subprocess.run(
            ["schtasks", "/Run", "/TN", task_name],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _service_running_windows(name: str) -> bool:
    try:
        out = subprocess.run(["sc", "query", name], capture_output=True, text=True, timeout=10)
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


def watchdog_loop(interval: int = 5, peer_service: str | None = None) -> None:
    log.info("watchdog started (interval=%ds, peer=%s)", interval, peer_service or "none")
    while True:
        if os.name == "nt":
            user_present = _any_user_logged_in()
            for image, task_name in WATCHED:
                # The tray is user-session-only; skip it when nobody is signed in.
                if image == "GuardianNodeTray.exe" and not user_present:
                    continue
                if not _process_running_windows(image):
                    log.warning("%s not running; re-running task %s", image, task_name)
                    _task_run_windows(task_name)
            # Revive the peer watchdog if it has been stopped.
            if peer_service and not _service_running_windows(peer_service):
                log.warning("peer service %s not running; starting it", peer_service)
                _service_start_windows(peer_service)
        else:
            unit = "guardiannode-agent.service"
            if not _service_running_systemd(unit):
                log.info("(dev) agent unit not active: %s", unit)
        time.sleep(interval)


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode watchdog")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--peer-service", default=None,
                        help="name of a sibling watchdog service to keep alive")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    watchdog_loop(args.interval, peer_service=args.peer_service)


if __name__ == "__main__":  # pragma: no cover
    cli()
