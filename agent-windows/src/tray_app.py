"""Child-visible system tray status and parent-dashboard shortcut."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Callable

from src.broker_client import BrokerClient
from src.config import AgentConfig, default_config_path
from src.pairing_client import load_credentials

log = logging.getLogger("guardiannode.tray")

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
    try:
        backend_url = BrokerClient().status().get("backend_url")
        if backend_url:
            return str(backend_url)
    except Exception:
        pass
    creds = load_credentials() or {}
    if creds.get("backend_url"):
        return creds["backend_url"]
    cfg = AgentConfig.from_path(default_config_path())
    return cfg.backend_url


def _device_id() -> str | None:
    try:
        device_id = BrokerClient().status().get("device_id")
        if device_id:
            return str(device_id)
    except Exception:
        pass
    creds = load_credentials() or {}
    return creds.get("device_id")


def pause_flow() -> None:
    """Pause is parent-authoritative and therefore lives in the signed-in dashboard."""
    _open_dashboard()


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
    try:
        return bool(BrokerClient().status().get("paused", False))
    except Exception:
        pass
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
            _open_dashboard()

        def _menu_exit(icon, item):  # noqa: ANN001
            icon.stop()

        def _status_text(*_args) -> str:
            # Diagnostics: which backend this device reports to + pairing state.
            try:
                status = BrokerClient().status()
                if status.get("paired"):
                    return f"Paired with {status.get('backend_url', '?')}"
            except Exception:
                pass
            creds = load_credentials() or {}
            if creds.get("device_token"):
                return f"Paired with {creds.get('backend_url', '?')}"
            return "Not paired yet"

        def _device_text(*_args) -> str:
            dev = _device_id()
            return f"Device ID: {dev}" if dev else "Device ID: —"

        menu = pystray.Menu(
            pystray.MenuItem(_status_text, None, enabled=False),
            pystray.MenuItem(_device_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause monitoring in parent dashboard", _menu_pause),
            pystray.MenuItem("Resume in parent dashboard", _menu_resume),
            pystray.MenuItem("Open dashboard", lambda *_: _open_dashboard()),
            pystray.MenuItem("Exit tray", _menu_exit),
        )
        icon = pystray.Icon("GuardianNode", green if not is_paused() else yellow, "GuardianNode", menu)
        icon.run()

    return _run


def _open_dashboard() -> None:
    import webbrowser
    url = _backend_url().rstrip("/")
    webbrowser.open(url)


def _self_test() -> None:
    """Validate dependencies required by the frozen tray without opening UI."""
    import _tkinter  # noqa: F401
    import pystray  # noqa: F401
    import tkinter as tk
    from PIL import Image  # noqa: F401

    interpreter = tk.Tcl()
    if not interpreter.eval("info patchlevel"):
        raise RuntimeError("Tcl interpreter did not report a version")


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode tray app")
    parser.add_argument("--config", default=str(default_config_path()))
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.self_test:
        _self_test()
        return

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
