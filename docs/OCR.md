# OCR

GuardianNode extracts visible text from screenshots using OCR and/or local
vision models.

## Engines

- **Primary**: PaddleOCR (Apache-2.0, accurate, ~300 MB)
- **Fallback**: Tesseract (Apache-2.0, smaller, ~50 MB)
- **None**: no classical OCR — the vision LLM reads text directly from the screenshot

Configurable: `OCR_ENGINE=paddle|tesseract|none`

## Pipeline

```
Visible Windows session
  ↓
Capture active-window screenshot
  ↓
Perceptual hash diff (skip if unchanged)
  ↓
Crop app-specific region if known
  ↓
Resize / grayscale / contrast (OpenCV)
  ↓
Run OCR
  ↓
Normalize whitespace
  ↓
Deduplicate (don't resend identical lines)
  ↓
Optional best-effort text filtering
  ↓
POST /api/events
```

## OCR cadence

- High-risk active apps (Roblox, Discord): every 2–5 seconds
- General capture cadence depends on policy/config
- Current installer defaults review the visible desktop; narrower app-gated
  capture is available through policy/config

## App-specific crop regions

Config in `agent-windows/ocr_regions/` per app:

```yaml
app: Roblox.exe
regions:
  chat_left:
    x_pct: 0.01
    y_pct: 0.10
    w_pct: 0.45
    h_pct: 0.55
```

Tunes accuracy and speed for known UIs.

## Dedupe

Per-app rolling cache of recently seen lines (LRU 200 entries). Identical lines within 60s are dropped.

## Confidence

Each OCR result includes the engine's confidence. Below `OCR_MIN_CONFIDENCE` (default 0.5), the event is dropped to reduce noise.

## Privacy

OCR text may contain sensitive visible content. Some paths apply best-effort
text filtering, but parents should not treat redaction as certain.
Screenshots and sensitive event fields are stored locally and encrypted when
retained for parent/admin review.
