# Capture queue housekeeping

Settings shows metadata-only counts for pending and quarantined captures,
automatic cleanup status, the configured policy, and any unfinished evidence
deletion requested during consent withdrawal. Counts never include image
contents, capture tokens, paths, window titles, URLs, or raw transport errors.

## Accepted work and restart recovery

The pending replay budget bounds one recovery pass. Valid accepted frames beyond
that budget remain encrypted on disk and are discovered on later refills; the
budget does not delete the rest of the backlog. Replay retains the current
newest-first policy and per-device queue fairness.

The pending-frame maximum age is a separate processing policy. An unreviewed
frame that expires before replay or classification moves to `pending_dead_letter`
with reason `capture_expired_before_review`. It is not presented as a completed
AI review. Normal quarantine housekeeping then applies. Settings exposes queue
and quarantine counts; individual quarantine inspection or reprocessing is still
an operator workflow, not a dashboard review feature.

Consent withdrawal, explicit evidence deletion and invalid authority still use
their deletion/discard paths. Recovery must not revive data after those actions.

## Quarantine policy

Normal housekeeping applies to `pending_dead_letter`, where failed captures
are quarantined. It does not expire live `pending` captures under this policy.
Defaults are seven days, a 256 MiB storage target, and 256 file unlink attempts
per pass. Parents can choose 1-90 days, 1 MiB-4 GiB, and 1-1,000 attempts.

The byte setting is an eventual housekeeping target, not an instantaneous disk
quota. Each scan examines at most 10,000 immediate directory entries, including
unrelated entries. Large inventories are processed across independent bounded
windows. Complete-cycle byte accounting and outstanding overage persist so
multiple individually small windows still converge toward the total target.
Partial scan sums restart safely after a service restart, and completed overage
is refreshed after a new complete scan or a policy change.

Age and eviction preference use file statistics; capture JSON is not opened.
For a complete frame, the newer member's modification time determines its age.
Eviction prefers older frames within the currently observed window. Locked
files, high insertion rates, large backlogs, or repeated restarts can delay
convergence. Truncated counts are lower bounds; a missing pair in one window
may have its other half in a different window. Failed attempts and exhausted
budgets are shown explicitly.

The worker runs a pass on startup and then on the configured interval (at least
60 seconds, one hour by default). Disabling automatic retention also disables
these scheduled attempts. An authenticated parent can still run cleanup from
Settings. No recursive traversal or symlink following is intended; generated
names, ordinary files, and owned immediate directories are checked, and
unrelated files are left alone. Host filesystem access controls remain required.

## Withdrawal deletion

An explicit withdrawal with deletion persists the generated capture targets in
the same database transaction as consent revocation and device credential
revocation, before unlinking queued captures. Failed deletion remains retryable
after restart. A token covers its ciphertext and metadata in both pending and
quarantine locations, so a later quarantine move does not escape the request.
Already-missing files are treated idempotently.

While that exact withdrawal remains current, later passes may discover late
files. After a new consent grant, retries remain limited to already recorded
targets, so new authorized captures are outside the old request. Unknown files
from an earlier truncated inventory remain visibly incomplete; an operator may
need to resolve unsafe files or damaged state and submit a new explicit
withdrawal/delete request. The service never broadens an old request silently.

Failed targets and file halves rotate behind untouched work. A separate retry
metadata budget is `min(4096, max(64, cleanup_batch_files * 8))`; unvisited
targets remain durable with conservative counters. Up to 20,000 target groups
are recorded, and overflow or malformed state remains marked incomplete.
Retained event/blob deletion continues through the existing pending-delete
lifecycle. The manual cleanup button retries those already requested deletions
as well as capture files. Backups, exports, snapshots and downloaded copies
are outside this operation.

## API and deployment

`GET /api/storage/capture-queue` returns status without sending notifications or
reading capture contents. `PATCH` on the same path updates selected policy
fields. `POST /api/storage/capture-queue/cleanup` runs one bounded pass and
returns status. All require a parent/admin role. Mutations also require recent
authentication and the application's CSRF protection.

State is stored in the existing settings table; this continuation adds no
database migration. Filesystem mutations are serialized within one backend
process. Multi-process workers and hostile host-level filesystem races are not
qualified by the portable tests. No empty queue or successful heartbeat should
be interpreted as proof that every screen was captured or classified.
