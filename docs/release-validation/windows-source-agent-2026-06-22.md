# Windows Source-Agent Validation — 2026-06-22

This note records source-level Windows validation performed during Phase 1
broker work. It is not a Windows installer qualification matrix.

## Host

| Field | Value |
|---|---|
| Host | `winprorunner` / `DESKTOP-3VMPQ20` |
| OS | Windows 11 `10.0.22000` |
| Python | `3.12.8` |
| Commit | `d61d0ad` |
| Repository path | `C:\Dashburg\repos\guardiannode` |

## Checks Run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .\agent-windows[dev,windows]
cd agent-windows
..\.venv\Scripts\python.exe -m compileall -q src tests
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check src tests
..\.venv\Scripts\python.exe -m pip install pyinstaller
..\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm guardiannode_agent.spec
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_windows_bundle.ps1
```

## Results

| Check | Result |
|---|---|
| Agent compile | Passed |
| Agent tests | `49 passed` |
| Agent Ruff | Passed |
| PyInstaller bundle | Passed |
| Bundle verifier | Passed |

The built bundle contained:

```text
GuardianNodeAgent.exe
GuardianNodeBroker.exe
GuardianNodeTray.exe
GuardianNodeWatchdog.exe
_internal\
```

## Not Run

- Inno Setup installer compile: `ISCC.exe` was not installed on this host.
- Clean all-in-one install.
- Clean child-only install.
- Standard child-account ACL test.
- Broker named-pipe security validation against a standard child account.
- Reboot, sleep/resume, Fast User Switching, upgrade, repair, rollback, or
  uninstall.
- SmartScreen/AV behavior and signing.

Windows installers remain **NO-GO** until the full clean-machine qualification
matrix passes.
