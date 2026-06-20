# Retention

Default retention by severity:

| Type | Retention | Configurable |
|---|---|---|
| Critical/high alerts | 90 days | ✅ |
| Medium alerts | 30 days | ✅ |
| Low/no-risk events | 24 hours | ✅ |
| Flagged screenshots | 30 days | ✅ |
| Audit logs | 180 days | ✅ |

## Cleanup worker

`backend/app/workers/cleanup_worker.py` runs hourly. Each pass deletes the
**whole record chain** for anything past its window — event → risk result →
alert → evidence-blob row → encrypted blob file on disk — via
`app/services/purge.py`, so cleanup never leaves orphaned rows or stray
evidence files.

Details:

1. Per severity tier, expired events and everything attached to them are removed.
2. Flagged screenshots age out on their own (shorter) window: the encrypted
   image file is deleted at 30 days while the alert metadata stays for the
   full alert retention, so you keep the context without keeping the picture.
3. A defensive sweep removes any evidence blob whose event has vanished.
4. Audit logs expire on their own schedule.

Deletion removes rows and files immediately. Freed disk sectors are not
separately overwritten (normal OS file deletion semantics).

## Parent controls

Dashboard **Settings → Retention** exposes per-severity retention sliders.
Dashboard **Storage** page shows current usage and offers:

- Wipe all screenshots
- Wipe all low-severity events (removes the events and risk results too, not just the alert rows)
- Wipe all events older than N days (full chain, including evidence files)
- Export everything as an encrypted package

Wipes are real deletions, not soft-deletes.

## Export format

`POST /api/storage/export` writes `<data>/exports/<id>.gnexport` — an AES-256-GCM
encrypted ZIP containing:

- `manifest.json` — export id, timestamp, format (`guardiannode-full-export-v2`), blob counts
- `alerts.jsonl`, `events.jsonl`, `risk_results.jsonl`, `audit_logs.jsonl`
- `evidence_manifest.json` — one entry per evidence blob (id, sha256, size, source event)
- `evidence/<blob_id>.enc` — the actual encrypted screenshot evidence files,
  byte-for-byte as stored on disk

The export is **local and parent-controlled**. Decrypting it (and the inner
`evidence/*.enc` files) requires this server's master key
(`<data>/keys/master.key`); each blob uses its `blob_id` as AES-GCM associated
data. There is no cloud upload and no recipient-key scheme. The dashboard
currently creates the export on the server filesystem and returns that local
path; remote browsers do not receive a streamed download.

## Audit

Every wipe and every export gets an `audit_logs` entry with timestamp, actor,
and what was deleted/exported.
