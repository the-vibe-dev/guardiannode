# Windows Agent

Runs on the child's PC in the signed-in Windows desktop session. It captures the
visible screen, OCRs visible text, sends screenshots to the backend for local
classification, and keeps a tray icon visible for pause/status actions.

The installer also registers a GuardianNode Endpoint Broker service and
watchdog components for resilience. Desktop capture still happens in the user's
interactive session because Windows service session 0 cannot reliably see the
child's desktop. In broker mode, the session process sends bounded screenshot
payloads over local IPC; the broker owns the device credential, durable queue,
pause state, and backend upload transport.

This broker path is experimental until it passes the clean Windows standard-user
matrix. Source testing without the broker can set `broker_enabled: false` in
`agent.yaml` or use `--dry-run`.

## Development setup

```bash
cd agent-windows
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate
pip install -e ".[dev]"
python -m src.main --dry-run
```

`--dry-run` prints what would be sent without making network calls.

To pair and run from Python source on a Windows child PC:

```powershell
cd agent-windows
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[windows]"
.\.venv\Scripts\python -m src.main --pair --server http://<server-ip>:8787 --code <pair-code>
.\.venv\Scripts\python -m src.main
```

Run the tray in a second terminal while testing from source:

```powershell
.\.venv\Scripts\python -m src.tray_app
```

## Configuration

Local config at `C:\ProgramData\GuardianNode\agent.yaml`:

```yaml
backend_url: http://127.0.0.1:8787
age_group: 10_13
ocr_engine: tesseract
ocr_cadence_seconds: 5
ocr_min_confidence: 0.5
phash_threshold: 2
full_screen_capture_enabled: true
monitored_apps:
  - notepad.exe
  - chrome.exe
  - msedge.exe
  - firefox.exe
  - brave.exe
```

In current installer builds, pairing credentials are intended to live under the
broker-owned `C:\ProgramData\GuardianNode\Secure\device.json`. A legacy
`C:\ProgramData\GuardianNode\device.json` may exist on upgraded alpha systems
and is migrated by the broker when possible.

## Components

- `main.py` — entrypoint, async loop
- `process_watcher.py` — `psutil`-based active process detection
- `window_tracker.py` — `pywin32` active window detection
- `screenshot_capture.py` — `mss`-based fast capture
- `ocr_engine.py` — Tesseract OCR wrapper; PaddleOCR is only a planned optional path
- `redactor.py` — best-effort text filtering helpers where used
- `durable_queue.py` — encrypted SQLite retry queue for screenshot payloads during outages
- `broker_protocol.py` — bounded versioned local IPC protocol
- `broker_client.py` — session-process client for the endpoint broker
- `broker_service.py` — privileged endpoint broker service entrypoint
- `backend_client.py` — HTTP client to backend
- `tray_app.py` — pystray-based notification icon and local pause UI
- `watchdog.py` — paired watchdog service using Windows Terminal Services APIs for active sessions
- `parent_auth.py` — Argon2id credential hashing helpers; recovery codes do not authorize tray actions

## Tests

```bash
pytest agent-windows/tests/
```

Some tests require Windows (`pywin32`); use the dry-run path on Linux.

## PyInstaller build

```powershell
cd agent-windows
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[windows]" pyinstaller
.\.venv\Scripts\pyinstaller --clean --noconfirm guardiannode_agent.spec
.\scripts\verify_windows_bundle.ps1
```

The shared bundle is written to `dist/GuardianNodeAgent/`. The release installer
expects that complete directory under `installer/build/prebuilt/agent`; see
[`POWER_USER_INSTALL.md`](POWER_USER_INSTALL.md) for the full installer build.
