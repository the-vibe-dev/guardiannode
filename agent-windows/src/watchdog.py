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
import csv
import logging
import os
import re
import subprocess
import time

log = logging.getLogger("guardiannode.watchdog")

# (process image, scheduled-task name) pairs the watchdog keeps alive.
WATCHED = [
    ("GuardianNodeAgent.exe", "GuardianNodeAgent"),
    ("GuardianNodeTray.exe", "GuardianNodeTray"),
]


def _parse_quser_session_ids(output: str) -> set[int]:
    sessions: set[int] = set()
    for line in output.splitlines():
        if "USERNAME" in line and "STATE" in line:
            continue
        m = re.search(r"\s+(\d+)\s+Active\s+", line)
        if m:
            sessions.add(int(m.group(1)))
    return sessions


def _parse_tasklist_session_ids(output: str) -> set[int]:
    sessions: set[int] = set()
    for row in csv.reader(output.splitlines()):
        if len(row) >= 4 and row[3].strip().isdigit():
            sessions.add(int(row[3].strip()))
    return sessions


def _active_user_session_ids_windows() -> set[int] | None:
    """Return active interactive session IDs, or None if quser is unavailable."""
    try:
        out = subprocess.run(["quser"], capture_output=True, text=True, timeout=10)
        if out.returncode != 0 and not (out.stdout or "").strip():
            if "No User exists" in (out.stderr or ""):
                return set()
            return None
        return _parse_quser_session_ids(out.stdout or "")
    except Exception:
        return None


def _process_session_ids_windows(image: str) -> set[int] | None:
    """Session IDs where an image exists. SYSTEM can see all user sessions."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None
        return _parse_tasklist_session_ids(out.stdout or "")
    except Exception:
        return None


def _process_running_windows(image: str) -> bool:
    sessions = _process_session_ids_windows(image)
    return bool(sessions)


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
            active_sessions = _active_user_session_ids_windows()
            user_present = bool(active_sessions) if active_sessions is not None else _any_user_logged_in()
            for image, task_name in WATCHED:
                # These are user-session tasks; skip them when nobody is signed in.
                if not user_present:
                    continue
                running_sessions = _process_session_ids_windows(image)
                missing_sessions: set[int] = set()
                if active_sessions is not None and running_sessions is not None:
                    missing_sessions = active_sessions - running_sessions
                    missing = bool(missing_sessions)
                else:
                    missing = not _process_running_windows(image)
                if missing:
                    detail = (
                        f" missing from sessions {sorted(missing_sessions)}"
                        if missing_sessions else ""
                    )
                    log.warning("%s not running%s; re-running task %s", image, detail, task_name)
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
