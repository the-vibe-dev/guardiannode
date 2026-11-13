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

## Parent-confirmed actions

An alert's action history shows the latest 50 commands, their delivery state,
the latest endpoint receipt, and an Undo control for reversible actions. The
parent-only `GET /api/alerts/{alert_id}/actions` API accepts `limit` from 1 to
100 and orders by creation time and command ID, newest first. Older audit
activity remains available through the Audit page.

Queued means the backend has accepted the command. Claimed means the endpoint
has taken it for execution. A success or failure is a receipt from that
execution; it is not continuous process telemetry. Refresh obtains the latest
stored receipts. Later local reconciliation can recover a failure without
rewriting the original command result.

An app pause can partly succeed. A failed receipt can therefore include active
pause leases, suspended processes, or pending resume work. The dashboard shows
that distinction and the last reported lease deadline. The command's delivery
deadline is separate from the app pause deadline. Missing counters mean the
endpoint did not report that measurement; they are not assumed to be zero.

Undo queues a separate command and does not claim instant release. New undo
commands identify the original pause, so undoing one lease does not remove a
different overlapping pause. Older endpoint commands without that identity
retain their original target-wide undo behavior. Deploy the matching backend,
dashboard, and endpoint together when evaluating these semantics.

The history API exposes only allowlisted booleans, counters, deadlines and
lease status from endpoint results. Raw agent error text and arbitrary result
fields are not returned in the history view. Known failures stay visible
without making an unqualified promise that every matching process was checked
or that no process remains paused.

## Upgrade and recovery boundary

Undo active app pauses with the old endpoint before upgrading it. Old journal
entries contain only numeric PIDs, which can be reused by unrelated processes.
The new endpoint preserves those entries as `legacy_unverified` and will not
guess which process to resume. An unreadable or corrupt journal is preserved
for verified operator recovery. Reboot/state recovery and the exact installed
Windows service must be qualified on an isolated Windows machine.

App restriction is reactive on the broker polling cadence, normally around ten
seconds plus polling/storage delays. It is not process-creation interception,
a daily screen-time budget, or a recurring schedule engine. See the Windows
agent README and review backlog for the native qualification matrix.
