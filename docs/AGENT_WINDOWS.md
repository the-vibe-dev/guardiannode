# Windows Agent

Runs as a Windows service on the child's PC. Watches monitored apps, OCRs visible text, sends events to the backend.

## Development setup

```bash
cd agent-windows
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate
pip install -e ".[dev]"
python -m src.main --dry-run
```

`--dry-run` prints what would be sent without making network calls.

## Configuration

Local config at `C:\ProgramData\GuardianNode\agent.yaml`:

```yaml
backend_url: http://127.0.0.1:8787
device_id: child-laptop-01
device_token: <encrypted>
ocr_engine: paddle
monitored_apps:
  - Roblox.exe
  - Discord.exe
  - chrome.exe
ocr_cadence_seconds: 5
```

## Components

- `main.py` — entrypoint, async loop
- `process_watcher.py` — `psutil`-based active process detection
- `window_tracker.py` — `pywin32` active window detection
- `screenshot_capture.py` — `mss`-based fast capture
- `ocr_engine.py` — pluggable PaddleOCR / Tesseract / none
- `redactor.py` — pre-transmission redaction
- `event_queue.py` — local SQLite queue for offline resilience
- `backend_client.py` — HTTP client to backend
- `tray_app.py` — pystray-based notification icon
- `tray_pause.py` — pause flow with password + duration
- `watchdog.py` — paired watchdog service
- `parent_auth.py` — Argon2id verification + recovery code

## Tests

```bash
pytest agent-windows/tests/
```

Some tests require Windows (`pywin32`); use the dry-run path on Linux.

## PyInstaller build

```bash
cd agent-windows
pyinstaller --noconfirm --windowed --name GuardianNodeAgent src/main.py
```

Output in `dist/GuardianNodeAgent/`.
