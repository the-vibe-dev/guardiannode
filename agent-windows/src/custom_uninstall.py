"""Custom uninstaller front-end.

Invoked by the Inno Setup uninstall hook. Prompts the parent for the password
(or recovery code), then chains to the real Inno Setup uninstaller.

The .iss script wires Programs & Features to call this exe; the real unins000
is launched only if the password verifies.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from src.parent_auth import verify_password, verify_recovery_code

log = logging.getLogger("guardiannode.uninstall")


def _ask_password() -> str | None:
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        val = simpledialog.askstring(
            "GuardianNode Uninstall",
            "Enter parent password (or 12-word recovery code) to uninstall:",
            show="*",
        )
        root.destroy()
        return val
    except Exception:
        # Console fallback
        try:
            from getpass import getpass
            return getpass("Parent password (or recovery code): ")
        except Exception:
            return None


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    real_uninstaller = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if real_uninstaller is None:
        log.error("usage: custom_uninstall.py <path-to-unins000.exe>")
        return 2

    pw = _ask_password()
    if not pw:
        log.info("uninstall cancelled (no password)")
        return 1
    if not (verify_password(pw) or verify_recovery_code(pw)):
        log.warning("incorrect parent password / recovery code")
        return 1

    log.info("parent verified — chaining to %s", real_uninstaller)
    return subprocess.call([str(real_uninstaller), "/SILENT"]) if os.name == "nt" else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
