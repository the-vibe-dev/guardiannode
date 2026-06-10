# Retention

Default retention by severity:

| Type | Retention | Configurable |
|---|---|---|
| Critical/high alerts | 90 days | ✅ |
| Medium alerts | 30 days | ✅ |
| Low/no-risk events | 24 hours or not stored | ✅ |
| Flagged screenshots | 30 days | ✅ |
| Raw OCR cache (unflagged) | 24 hours | ✅ |
| Audit logs | 180 days | ✅ |

## Cleanup worker

`backend/app/workers/cleanup_worker.py` runs hourly:
1. Finds expired rows per the retention table.
2. Drops associated evidence blobs from disk first.
3. Then deletes DB rows.
4. Vacuums SQLite to reclaim disk space (weekly).

## Parent controls

Dashboard **Settings → Retention** exposes per-severity retention sliders.
Dashboard **Storage** page shows current usage and offers:
- Wipe all screenshots
- Wipe all low-severity events
- Wipe all events older than N days
- Export everything as encrypted ZIP, then wipe

## Export format

Encrypted ZIP containing:
- `alerts.json` (JSON Lines)
- `events.json` (JSON Lines)
- `screenshots/` (encrypted blobs + manifest)
- `manifest.json` with SHA-256 hashes
- Encrypted with the master key + recipient public key if provided

## Audit

Every wipe and every export gets an `audit_logs` entry with timestamp, actor, and what was deleted/exported.
