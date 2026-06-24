"""Watchdog process (runs as a SYSTEM service).

The agent and tray run per user session via scheduled tasks (Windows services
live in session 0 and cannot touch a user's desktop). This watchdog provides
resilience: if either disappears, it relaunches the missing executable in each
active user session. Disconnected RDP sessions are observed but not relaunched
until they become active again; locked local sessions remain active from the
Terminal Services perspective and keep their existing agent/tray process.

The production installer runs one GuardianNode-branded watchdog service and
uses SCM/WinSW recovery to restart it if it crashes. Ending the service still
requires administrator rights; the backend also raises an alert when a device
stops sending heartbeats — see the offline monitor.
"""
from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

log = logging.getLogger("guardiannode.watchdog")

# (process image, scheduled-task name) pairs the watchdog keeps alive.
WATCHED = [
    ("GuardianNodeAgent.exe", "GuardianNodeAgent"),
    ("GuardianNodeTray.exe", "GuardianNodeTray"),
]
MAINTENANCE_MARKER = Path(
    os.environ.get(
        "GUARDIANNODE_MAINTENANCE_FLAG",
        str(
            Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
            / "GuardianNode"
            / "Secure"
            / "maintenance.flag"
        ),
    )
)

WTS_ACTIVE = 0
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = -1
CREATE_NEW_CONSOLE = 0x00000010
CREATE_UNICODE_ENVIRONMENT = 0x00000400


class _WtsSessionInfo(ctypes.Structure):
    _fields_ = [
        ("SessionId", wintypes.DWORD),
        ("pWinStationName", wintypes.LPWSTR),
        ("State", wintypes.DWORD),
    ]


class _ProcessEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * wintypes.MAX_PATH),
    ]


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class SessionApi(Protocol):
    def active_user_session_ids(self) -> set[int] | None: ...
    def process_session_ids(self, image: str) -> set[int] | None: ...
    def launch_in_session(self, session_id: int, executable: Path) -> bool: ...


class WindowsSessionApi:
    """Thin ctypes wrapper around Terminal Services and process APIs."""

    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
        self._advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._userenv = ctypes.WinDLL("userenv", use_last_error=True)
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        session_info_ptr = ctypes.POINTER(_WtsSessionInfo)
        self._wtsapi32.WTSEnumerateSessionsW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(session_info_ptr),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._wtsapi32.WTSEnumerateSessionsW.restype = wintypes.BOOL
        self._wtsapi32.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        self._wtsapi32.WTSFreeMemory.restype = None
        self._wtsapi32.WTSQueryUserToken.argtypes = [
            wintypes.ULONG,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        self._wtsapi32.WTSQueryUserToken.restype = wintypes.BOOL

        self._kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self._kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self._kernel32.Process32FirstW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessEntry32),
        ]
        self._kernel32.Process32FirstW.restype = wintypes.BOOL
        self._kernel32.Process32NextW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessEntry32),
        ]
        self._kernel32.Process32NextW.restype = wintypes.BOOL
        self._kernel32.ProcessIdToSessionId.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

        self._userenv.CreateEnvironmentBlock.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.BOOL,
        ]
        self._userenv.CreateEnvironmentBlock.restype = wintypes.BOOL
        self._userenv.DestroyEnvironmentBlock.argtypes = [ctypes.c_void_p]
        self._userenv.DestroyEnvironmentBlock.restype = wintypes.BOOL

        self._advapi32.CreateProcessAsUserW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(_StartupInfo),
            ctypes.POINTER(_ProcessInformation),
        ]
        self._advapi32.CreateProcessAsUserW.restype = wintypes.BOOL

    def active_user_session_ids(self) -> set[int] | None:
        session_info_ptr = ctypes.POINTER(_WtsSessionInfo)
        sessions = session_info_ptr()
        count = wintypes.DWORD()
        ok = self._wtsapi32.WTSEnumerateSessionsW(
            wintypes.HANDLE(0),
            0,
            1,
            ctypes.byref(sessions),
            ctypes.byref(count),
        )
        if not ok:
            log.warning("WTSEnumerateSessionsW failed: %s", ctypes.get_last_error())
            return None
        try:
            return {
                int(sessions[i].SessionId)
                for i in range(count.value)
                if int(sessions[i].State) == WTS_ACTIVE
            }
        finally:
            self._wtsapi32.WTSFreeMemory(sessions)

    def process_session_ids(self, image: str) -> set[int] | None:
        snapshot = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == wintypes.HANDLE(INVALID_HANDLE_VALUE).value:
            log.warning("CreateToolhelp32Snapshot failed: %s", ctypes.get_last_error())
            return None
        try:
            entry = _ProcessEntry32()
            entry.dwSize = ctypes.sizeof(_ProcessEntry32)
            ok = self._kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            sessions: set[int] = set()
            wanted = image.casefold()
            while ok:
                if entry.szExeFile.casefold() == wanted:
                    session_id = wintypes.DWORD()
                    if self._kernel32.ProcessIdToSessionId(
                        entry.th32ProcessID,
                        ctypes.byref(session_id),
                    ):
                        sessions.add(int(session_id.value))
                ok = self._kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            return sessions
        finally:
            self._kernel32.CloseHandle(snapshot)

    def launch_in_session(self, session_id: int, executable: Path) -> bool:
        if not executable.exists():
            log.warning("cannot launch missing executable: %s", executable)
            return False
        token = wintypes.HANDLE()
        if not self._wtsapi32.WTSQueryUserToken(session_id, ctypes.byref(token)):
            log.warning(
                "WTSQueryUserToken failed for session %s: %s",
                session_id,
                ctypes.get_last_error(),
            )
            return False
        environment = ctypes.c_void_p()
        environment_created = False
        try:
            environment_created = bool(
                self._userenv.CreateEnvironmentBlock(ctypes.byref(environment), token, False)
            )
            startup = _StartupInfo()
            startup.cb = ctypes.sizeof(_StartupInfo)
            startup.lpDesktop = "winsta0\\default"
            process_info = _ProcessInformation()
            command = ctypes.create_unicode_buffer(f'"{executable}"')
            ok = self._advapi32.CreateProcessAsUserW(
                token,
                None,
                command,
                None,
                None,
                False,
                CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT,
                environment if environment_created else None,
                str(executable.parent),
                ctypes.byref(startup),
                ctypes.byref(process_info),
            )
            if not ok:
                log.warning(
                    "CreateProcessAsUserW failed for session %s: %s",
                    session_id,
                    ctypes.get_last_error(),
                )
                return False
            self._kernel32.CloseHandle(process_info.hThread)
            self._kernel32.CloseHandle(process_info.hProcess)
            return True
        finally:
            if environment_created:
                self._userenv.DestroyEnvironmentBlock(environment)
            self._kernel32.CloseHandle(token)


_SESSION_API: SessionApi | None = None


def _session_api_windows() -> SessionApi | None:
    global _SESSION_API
    if os.name != "nt":
        return None
    if _SESSION_API is None:
        try:
            _SESSION_API = WindowsSessionApi()
        except Exception:
            log.exception("failed to initialize Windows session API")
            return None
    return _SESSION_API


def _active_user_session_ids_windows(api: SessionApi | None = None) -> set[int] | None:
    resolved = api or _session_api_windows()
    if resolved is None:
        return None
    return resolved.active_user_session_ids()


def _process_session_ids_windows(image: str, api: SessionApi | None = None) -> set[int] | None:
    resolved = api or _session_api_windows()
    if resolved is None:
        return None
    return resolved.process_session_ids(image)


def _process_running_windows(image: str, api: SessionApi | None = None) -> bool:
    sessions = _process_session_ids_windows(image, api)
    return bool(sessions)


def _resolve_watched_exe(image: str) -> Path:
    """Resolve a watched executable beside the frozen watchdog when possible."""
    executable = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    directory = executable.parent
    candidate = directory / image
    if candidate.exists():
        return candidate
    return Path.cwd() / image


def _launch_process_in_session_windows(
    session_id: int,
    executable: Path,
    api: SessionApi | None = None,
) -> bool:
    resolved = api or _session_api_windows()
    if resolved is None:
        return False
    return resolved.launch_in_session(session_id, executable)


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


def _maintenance_mode_active() -> bool:
    return MAINTENANCE_MARKER.exists()


def watchdog_once(peer_service: str | None = None, api: SessionApi | None = None) -> None:
    if _maintenance_mode_active():
        log.info("installer maintenance marker present; watchdog repair actions paused")
        return

    if os.name == "nt":
        resolved_api = api or _session_api_windows()
        active_sessions = _active_user_session_ids_windows(resolved_api)
        user_present = bool(active_sessions) if active_sessions is not None else True
        for image, task_name in WATCHED:
            # These are user-session tasks; skip them when nobody is signed in.
            if not user_present:
                continue
            running_sessions = _process_session_ids_windows(image, resolved_api)
            missing_sessions: set[int] = set()
            if active_sessions is not None and running_sessions is not None:
                missing_sessions = active_sessions - running_sessions
                missing = bool(missing_sessions)
            else:
                missing = not _process_running_windows(image, resolved_api)
            if missing:
                detail = (
                    f" missing from sessions {sorted(missing_sessions)}"
                    if missing_sessions else ""
                )
                log.warning("%s not running%s", image, detail)
                all_launched = bool(missing_sessions)
                for session_id in sorted(missing_sessions):
                    exe = _resolve_watched_exe(image)
                    if not _launch_process_in_session_windows(session_id, exe, resolved_api):
                        all_launched = False
                if not all_launched:
                    log.warning("falling back to scheduled task %s", task_name)
                    _task_run_windows(task_name)
        # Revive the peer watchdog if it has been stopped.
        if peer_service and not _service_running_windows(peer_service):
            log.warning("peer service %s not running; starting it", peer_service)
            _service_start_windows(peer_service)
    else:
        unit = "guardiannode-agent.service"
        if not _service_running_systemd(unit):
            log.info("(dev) agent unit not active: %s", unit)


def watchdog_loop(interval: int = 5, peer_service: str | None = None) -> None:
    log.info("watchdog started (interval=%ds, peer=%s)", interval, peer_service or "none")
    while True:
        watchdog_once(peer_service=peer_service)
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
