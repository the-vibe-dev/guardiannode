"""System tray icon + pause UX.

Right-click → Pause → enter password → pick duration → POST to backend.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx

from src.config import AgentConfig, default_config_path
from src.pairing_client import load_credentials
from src.parent_auth import verify_password

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


def _verify_parent_password(s: str) -> bool:
    # Local hash file (all-in-one installs that provisioned parent.json).
    if verify_password(s):
        return True
    # Child-only installs have no local parent hash. Never send a parent
    # password over plaintext LAN HTTP; only allow remote verification over
    # HTTPS or loopback.
    try:
        backend_url = _backend_url().rstrip("/")
        parsed = urlparse(backend_url)
        is_loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        if parsed.scheme != "https" and not is_loopback:
            log.warning("refusing remote parent-password check over non-HTTPS backend URL")
            return False
        with httpx.Client(timeout=10.0) as c:
            r = c.post(
                f"{backend_url}/api/auth/login",
                json={"password": s},
            )
            return r.status_code == 200
    except Exception as e:
        log.warning("online parent-password check failed: %s", e)
        return False


# --- Dialogs ---------------------------------------------------------------
#
# pystray menu callbacks run inside the tray's win32 message loop. Creating a
# Tk window there never reliably gets foreground focus, so the password field
# ignored keystrokes and the OK/Cancel buttons didn't respond. We therefore
# render every dialog in a SEPARATE PROCESS (a re-exec of this same exe with
# `--prompt`), which has its own clean main thread and message loop. The child
# writes the result as JSON to a temp file we hand it.


def _new_root(title: str) -> "tk.Tk":
    root = tk.Tk()
    root.title(title)
    root.attributes("-topmost", True)
    root.lift()
    root.after(50, root.focus_force)
    return root


def _ask_password_dialog() -> str | None:
    result: dict = {"value": None}
    root = _new_root("GuardianNode — Parent verification")
    root.geometry("380x170")
    tk.Label(root, text="Enter your parent password:").pack(pady=(14, 6))
    entry = tk.Entry(root, show="*", width=36)
    entry.pack(pady=4)
    entry.focus_set()

    def _ok(*_):
        result["value"] = entry.get()
        root.destroy()

    def _cancel(*_):
        result["value"] = None
        root.destroy()

    btns = tk.Frame(root)
    btns.pack(pady=12)
    tk.Button(btns, text="OK", width=10, command=_ok, default="active").pack(side="left", padx=6)
    tk.Button(btns, text="Cancel", width=10, command=_cancel).pack(side="left", padx=6)
    root.bind("<Return>", _ok)
    root.bind("<Escape>", _cancel)
    root.protocol("WM_DELETE_WINDOW", _cancel)
    root.mainloop()
    return result["value"]


def _ask_duration_dialog() -> int | None:
    result: dict = {"value": None}
    root = _new_root("Pause GuardianNode")
    root.geometry("300x230")
    tk.Label(root, text="Pause monitoring for:").pack(pady=10)
    for label, seconds in DURATIONS:
        def _pick(s=seconds):
            result["value"] = s
            root.destroy()
        tk.Button(root, text=label, command=_pick, width=22).pack(pady=2)
    tk.Button(root, text="Cancel", command=root.destroy, width=22).pack(pady=(8, 2))
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return result["value"]


def _run_prompt_in_subprocess(kind: str) -> str | None:
    """Re-exec this exe with --prompt <kind> to render the dialog cleanly."""
    fd, out_path = tempfile.mkstemp(suffix=".gnprompt")
    os.close(fd)
    try:
        if getattr(sys, "frozen", False):
            args = [sys.executable, "--prompt", kind, "--out", out_path]
        else:
            args = [sys.executable, os.path.abspath(__file__), "--prompt", kind, "--out", out_path]
        creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        subprocess.run(args, timeout=300, creationflags=creationflags)
        raw = Path(out_path).read_text("utf-8") or "{}"
        return json.loads(raw).get("value")
    except Exception as e:
        log.warning("prompt subprocess failed (%s); falling back to in-process dialog", e)
        # Fallback keeps Exit/Pause usable even if the re-exec path breaks.
        if kind == "password":
            return _ask_password_dialog()
        if kind == "duration":
            d = _ask_duration_dialog()
            return str(d) if d else None
        return None
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def _ask_password() -> str | None:
    return _run_prompt_in_subprocess("password")


def _ask_duration() -> int | None:
    val = _run_prompt_in_subprocess("duration")
    try:
        return int(val) if val else None
    except (TypeError, ValueError):
        return None


def pause_flow() -> None:
    pw = _ask_password()
    if not pw:
        return
    if not _verify_parent_password(pw):
        log.warning("incorrect parent password")
        return
    duration = _ask_duration()
    if not duration:
        return
    device_id = _device_id()
    if not device_id:
        log.warning("device not paired; cannot pause")
        return
    try:
        # Local tray pause is enforced by the capture loop. Dashboard-visible
        # pause is available through the authenticated parent dashboard.
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
            if pw and _verify_parent_password(pw):
                icon.stop()

        def _status_text(*_args) -> str:
            # Diagnostics: which backend this device reports to + pairing state.
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
            pystray.MenuItem("Pause monitoring", _menu_pause),
            pystray.MenuItem("Resume", _menu_resume),
            pystray.MenuItem("Open dashboard", lambda *_: _open_dashboard()),
            pystray.MenuItem("Exit tray (parent password required)", _menu_exit),
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
    from PIL import Image  # noqa: F401

    interpreter = tk.Tcl()
    if not interpreter.eval("info patchlevel"):
        raise RuntimeError("Tcl interpreter did not report a version")


def cli() -> None:
    parser = argparse.ArgumentParser(description="GuardianNode tray app")
    parser.add_argument("--config", default=str(default_config_path()))
    parser.add_argument("--prompt", choices=["password", "duration"], help=argparse.SUPPRESS)
    parser.add_argument("--out", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.self_test:
        _self_test()
        return

    # Dialog-rendering mode: a clean child process with its own main thread.
    # Must run BEFORE the single-instance mutex so the tray can spawn it.
    if args.prompt:
        value = None
        if args.prompt == "password":
            value = _ask_password_dialog()
        elif args.prompt == "duration":
            d = _ask_duration_dialog()
            value = str(d) if d else None
        if args.out:
            try:
                Path(args.out).write_text(json.dumps({"value": value}), encoding="utf-8")
            except Exception as e:
                log.warning("could not write prompt result: %s", e)
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
