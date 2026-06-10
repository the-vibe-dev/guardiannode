# GuardianNode Windows Agent

Runs as a Windows service on the child's PC. Monitors approved apps, OCRs visible text, sends events to the backend.

See [../docs/AGENT_WINDOWS.md](../docs/AGENT_WINDOWS.md) for full setup.

## Dev install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m src.main --dry-run
```

The source builds on Linux (for dev/testing), but production deployment is Windows-only.

## Components

- `src/main.py` — entrypoint
- `src/config.py` — config loading
- `src/process_watcher.py` — psutil-based active process detection
- `src/window_tracker.py` — pywin32 active window detection (Windows only)
- `src/screenshot_capture.py` — mss-based capture
- `src/ocr_engine.py` — pluggable OCR
- `src/redactor.py` — pre-transmission redaction
- `src/event_queue.py` — offline queue
- `src/backend_client.py` — HTTP client to backend
- `src/tray_app.py` — tray icon + pause UX
- `src/watchdog.py` — paired watchdog
- `src/hardware_probe.py` — hardware detection for the installer
- `src/pairing_client.py` — pairing handshake
