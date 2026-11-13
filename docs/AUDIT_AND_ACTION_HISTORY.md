# Audit and action history

## Audit history

The parent Audit page browses retained server history rather than a fixed client
download. Apply filters for exact actor and action, metadata text, and local
calendar dates. The browser converts the selected date bounds to timezone-aware
UTC: From is inclusive and Through includes that whole local day. Search covers
actor, action, target and source IP; it does not search arbitrary audit details
or evidence content. Retention still determines which records exist.

`GET /api/audit/page` requires a parent session. Its response is
`{items, next_cursor, total}`. The default page size is 50, maximum 100. Filters
are `actor`, `action`, `q`, `since` (inclusive), and `until` (exclusive).
Time bounds require a timezone. Each opaque cursor binds the current filters
and the last `(created_at, id)` position. Keep the same filters on later pages;
start over after changing them. Deleted anchor rows do not invalidate the
position, and newer inserted rows do not cause old rows to repeat. This is a
live history view, not a transactionally frozen export, so totals can change
with new activity and retention cleanup. The legacy `/api/audit` list endpoint
remains available for existing callers.

The dashboard gives each applied filter set its own query identity, displays
load failures and retries, and keeps later-page failures separate from the
already loaded records. Unsaved filter edits do not silently change the query.

## Evidence actions and historical recovery

The current alert workflow supports review notes, useful/false-positive feedback,
notification and evidence deletion. Device restrictions and child notices cannot
be created. New request creation and exception approvals are retired.

An alert's history keeps the latest 50 stored actions, their delivery state and
allowlisted execution metadata. The parent-only
`GET /api/alerts/{alert_id}/actions` endpoint accepts a limit of 1 to 100 and
orders by creation time and command ID, newest first. Older audit activity can
be found on the Audit page. Raw agent error strings and arbitrary result fields
are not returned in the history view.

Existing restriction records retain recovery controls where appropriate. Undo
queues a release-only command. Queued means accepted by the backend; claimed
means collected by an endpoint. Neither is a success receipt. Missing counters
mean not reported, not zero. The current endpoint also attempts local recovery
from verified old journals without creating new restrictions.

A receipt records a past execution, not continuous process telemetry. Subsequent
local recovery can resolve a failed release without changing an older receipt.
See [legacy restriction recovery](ENFORCEMENT.md) before upgrading a device.
