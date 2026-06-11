"""System tray icon + pause UX.

Right-click → Pause → enter password → pick duration → POST to backend.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import simpledialog
from typing import Callable

import httpx

from src.config import AgentConfig, default_config_path
from src.pairing_client import load_credentials
from src.parent_auth import verify_password, verify_recovery_code

log = logging.getLogger("guardiannode.tray")

DURATIONS = [
    ("15 minutes", 15 * 60),
    ("1 hour", 60 * 60),
    ("4 hours", 4 * 60 * 60),
    ("Until reboot", 86400),  # ~24h cap; service restart resets
]


# Held for the process lifetime so the OS keeps the mutex alive.
_instance_mutex = None


def already_running() -> bool:
    """Single-instance guard: a second tray launch in the same session exits.

    Session-local (not Global\\) on purpose — each logged-in user gets their
    own tray icon, but duplicate launchers within a session (startup shortcut
    + taskbar pin + installer) collapse to one.
    """
    global _instance_mutex
    if os.name != "nt":
        return False
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "GuardianNodeTraySingleton")
    return ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def _backend_url() -> str:
    creds = load_credentials() or {}
    if creds.get("backend_url"):
        return creds["backend_url"]
    cfg = AgentConfig.from_path(default_config_path())
    return cfg.backend_url


def _device_id() -> str | None:
    creds = load_credentials() or {}
    return creds.get("device_id")


def _device_token() -> str | None:
    creds = load_credentials() or {}
    return creds.get("device_token")


def _verify_password_or_recovery(s: str) -> bool:
    if verify_password(s):
        return True
    return verify_recovery_code(s)


def _ask_password() -> str | None:
    root = tk.Tk()
    root.withdraw()
    val = simpledialog.askstring(
        "GuardianNode — Parent verification",
        "Enter your parent password (or 12-word recovery code):",
        show="*",
    )
    root.destroy()
    return val


def _ask_duration() -> int | None:
    root = tk.Tk()
    root.title("Pause GuardianNode")
    root.geometry("280x180")
    selected: dict = {"value": None}

    tk.Label(root, text="Pause monitoring for:").pack(pady=10)
    for label, seconds in DURATIONS:
        def _pick(s=seconds):
            selected["value"] = s
            root.destroy()
        tk.Button(root, text=label, command=_pick, width=20).pack(pady=2)
    tk.Button(root, text="Cancel", command=root.destroy, width=20).pack(pady=2)

    root.mainloop()
    return selected.get("value")


def pause_flow() -> None:
    pw = _ask_password()
    if not pw:
        return
    if not _verify_password_or_recovery(pw):
        log.warning("incorrect parent password")
        return
    duration = _ask_duration()
    if not duration:
        return
    device_id = _device_id()
    token = _device_token()
    if not device_id:
        log.warning("device not paired; cannot pause")
        return
    try:
        # Local pause is enforced by the backend rejecting events anyway,
        # but we tell the backend so the dashboard shows the pause.
        # We use the user session cookie or a dedicated agent pause endpoint.
        # For v1 we POST to a hypothetical /api/devices/{id}/pause-via-device.
        # In the current backend, device pause is admin-only; a local flag file
        # is the v1 path that the capture loop checks.
        _set_local_pause(duration)
        log.info("paused locally for %d seconds", duration)
    except Exception as e:
        log.warning("pause failed: %s", e)


def _pause_flag_path() -> str:
    if os.name == "nt":
        return os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "GuardianNode", "paused_until")
    return os.path.expanduser("~/.guardiannode/paused_until")


def _set_local_pause(duration_seconds: int) -> None:
    import time as _t
    path = _pause_flag_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(int(_t.time()) + duration_seconds))


def is_paused() -> bool:
    import time as _t
    path = _pause_flag_path()
    try:
        with open(path, encoding="utf-8") as f:
            until = int(f.read().strip())
        return _t.time() < until
    except Exception:
        return False


def _try_pystray() -> Callable[[], None] | None:
    """Return a runner if pystray is available, else None."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def _make_image(color: str) -> "Image.Image":
        img = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=color)
        return img

    def _load_brand_icon() -> "Image.Image | None":
        """Find the GuardianNode logo: PyInstaller bundle dir, exe dir, or repo."""
        candidates = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "icon.png")
        candidates.append(Path(sys.executable).resolve().parent / "icon.png")
        candidates.append(Path(__file__).resolve().parents[2] / "assets" / "brand" / "icon.png")
        for p in candidates:
            try:
                if p.is_file():
                    return Image.open(p).convert("RGBA").resize((64, 64))
            except Exception:
                continue
        return None

    def _paused_variant(base: "Image.Image") -> "Image.Image":
        img = base.copy()
        d = ImageDraw.Draw(img)
        d.ellipse((36, 36, 62, 62), fill="#f9a825", outline="white", width=2)
        return img

    def _run() -> None:
        brand = _load_brand_icon()
        green = brand or _make_image("#275e3d")
        yellow = _paused_variant(brand) if brand else _make_image("#f9a825")

        def _menu_pause(icon, item):  # noqa: ANN001
            pause_flow()
            icon.icon = yellow if is_paused() else green

        def _menu_resume(icon, item):  # noqa: ANN001
            try:
                os.remove(_pause_flag_path())
            except OSError:
                pass
            icon.icon = green

        def _menu_exit(icon, item):  # noqa: ANN001
            pw = _ask_password()
            if pw and _verify_password_or_recovery(pw):
                icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Pause monitoring", _menu_pause),
            pystray.MenuItem("Resume", _menu_resume),
            pystray.MenuItem("Open dashboard", lambda *_: _open_dashboard()),
            pystray.MenuItem("Exit (parent password required)", _menu_exit),
        )
        icon = pystray.Icon("GuardianNode", green if not is_paused() else yellow, "GuardianNode", menu)
        icon.run()

    return _run


def _open_dashboard() -> None:
    import webbrowser
    url = _backend_url().rstrip("/")
    webbrowser.open(url)


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode tray app")
    parser.add_argument("--config", default=str(default_config_path()))
    args = parser.parse_args()  # noqa: F841

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if already_running():
        log.info("another GuardianNode tray instance is already running in this session; exiting")
        return

    runner = _try_pystray()
    if runner is None:
        log.warning("pystray not installed; running console fallback. Use ctrl+c to quit.")
        # Console fallback: just exit; on Windows the .exe stub will use pystray.
        return
    runner()


if __name__ == "__main__":  # pragma: no cover
    cli()
