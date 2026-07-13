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
- Download or delete existing encrypted exports

Wipes are real deletions, not soft-deletes.

## Export format

`POST /api/storage/export` writes `<data>/exports/<id>.gna` — a complete,
same-instance GuardianNode Archive Format v1 snapshot containing an exact
SQLite backup, lossless typed records, encrypted evidence, configuration,
component versions, and a signed manifest covering every file and hash.

The dashboard snapshot is **local and parent-controlled** and remains tied to
the instance master key. Use `guardiannode-archive create` with a passphrase or
offline recovery public key when a clean-host portable archive is required.
The dashboard lists `.gna` files and any legacy `.gnexport` files and downloads
them through the authenticated `GET /api/storage/exports/<id>/download`
endpoint. Deleting an export removes only the selected archive and writes an
audit-log entry. Legacy `.gnexport` files are incomplete and are supported only
for download or deletion.

## Audit

Every wipe and every export gets an `audit_logs` entry with timestamp, actor,
and what was deleted/exported.
