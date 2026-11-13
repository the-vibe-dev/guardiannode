# GuardianNode Windows Agent

Runs a visible capture process in each active Windows user session, with a
SYSTEM broker that owns enrollment credentials, encrypted queue storage,
backend transport, and parent-issued actions. The backend performs screenshot
OCR/classification; the child-visible tray reports status.

See [../docs/AGENT_WINDOWS.md](../docs/AGENT_WINDOWS.md) for full setup.

## Dev install

```bash
uv sync --frozen --extra dev
uv run python -m src.main --dry-run
```

The source builds on Linux (for dev/testing), but production deployment is Windows-only.

## Components

- `src/main.py` — entrypoint
- `src/config.py` — config loading
- `src/process_watcher.py` — psutil-based active process detection
- `src/window_tracker.py` — pywin32 active window detection (Windows only)
- `src/screenshot_capture.py` — mss-based capture
- `src/ocr_engine.py` — optional local OCR helpers
- `src/broker_service.py` — credentialed Windows broker and parent-policy cache
- `src/broker_client.py` / `src/broker_protocol.py` — bounded local capture/status IPC
- `src/durable_queue.py` — encrypted SQLite screenshot queue for backend outages
- `src/backend_client.py` — HTTP client to backend
- `src/tray_app.py` — tray icon + pause UX
- `src/watchdog.py` — keeps the visible tray running in active sessions
- `src/enforcement.py` — parent-confirmed reversible endpoint actions
- `src/family_tls.py` — enrolled family-CA transport verification
- `src/hardware_probe.py` — hardware detection for the installer
- `src/pairing_client.py` — pairing handshake

## Recovery behavior

Production capture starts disabled until the backend provides an explicitly
enabled monitoring policy. Disabling screenshot/retention consent or revoking
enrollment stops new capture and removes pending upload frames once the device
receives the change. An ordinary network outage preserves its last received
permitted policy; a disconnected device cannot learn a new parent choice until
it reconnects. The tray displays monitoring-off and paused states.
Disabling separate app/URL metadata removes those fields from new submissions,
rewrites pending encrypted queue rows, and filters already claimed frames before
upload. Screenshot pixels can still contain visible app names or addresses;
the screenshot choice controls collection of those images.

The broker retries a pending enrollment after transient startup/network errors
and reloads saved credentials before each screenshot upload. Rejected or
expired pairing codes still require a fresh code from the parent; temporary
HTTP failures do not erase a pending code.

Parent capture settings and pause deadlines are saved in broker-owned storage.
The capture process waits for the broker policy before its first frame. A
remote parent pause reaches the broker during its normal control poll and
stops new screenshot queue submissions; the cached deadline remains effective
if the backend disconnects or the broker restarts. Its expiry permits normal
capture to resume. An explicit parent resume takes effect on the next poll.

Offline screenshot storage remains bounded by the configured age, item, and
byte limits. Expired frames are pruned on startup, before dequeue, and when
reporting backlog, even when no new capture arrives. This is bounded buffering,
not an indefinite archive or a guarantee that every offline frame is retained.

## Parent app pauses

An app pause is an explicit, bounded parent action for one absolute Windows
executable path, for 15 minutes, 1 hour, or 24 hours. During that lease the broker
checks for matching running processes on its normal control poll (normally
every 10 seconds, subject to polling and storage delays). A newly launched copy
of the same executable is paused on a subsequent check. This does not prevent
an application from starting or cover a renamed executable, another path, or
every application in the same product family.

The protected action journal records each process's PID, creation time and
Windows-normalized executable path before suspension. Release verifies all
three identity fields and uses psutil's additional PID-reuse checks. Overlapping
leases share one suspension. Expiry or undo releases it only when no matching
lease remains; a newly authorized lease also cancels an earlier failed release.
New undo commands select the original command ID. Older target-wide undo
commands still release all matching leases, and replaying that same undo does
not cancel a later parent pause.

The journal uses a flushed temporary file and atomic replacement. If the
completion write fails after a new suspension, the broker attempts immediate
rollback using the same process identity. If release is denied, the identity
stays available for recovery and later retries. Completed command records remain
for seven days, longer than the server's 24-hour delivery window, so a lost
acknowledgement does not restart an expired or undone pause. The broker's
serialized control loop is the journal's single writer.

Known critical Windows process names, the broker and its ancestors, GuardianNode
executables, the broker's own executable, and recognized Windows service
accounts are excluded. An unreadable process owner is not acted on. An already
stopped process without a GuardianNode recovery record is not adopted or later
resumed. These guards do not claim to identify every third-party security product.
No additional capture, automatic parent decisions, or unrelated process history
is introduced by app-pause reconciliation.

Command results distinguish confirmed suspensions, new suspensions, successful
resumes, failures, protected skips, incomplete scans, pending recovery, and
active leases. A partial failure is reported as `failed`, with its counters and
remaining lease status: some matching processes may still be paused and the
bounded lease can remain active. Subsequent recovery is retried locally; the
original command result describes its execution, not continuous live telemetry.

Unreadable or malformed journals are preserved and block new process actions;
the broker continues its heartbeat and consent-policy polling. Do not delete a
recovery journal to clear an error while processes may still be suspended.
Older builds stored only numeric PIDs. Before upgrading such a build, undo every
active app pause and verify that the apps run. The new broker preserves old
PID-only records as `legacy_unverified` and never guesses which current process
to resume. Existing unresolved records require operator recovery with a verified
process identity, or a managed device restart and a review of the preserved
state.

Linux unit tests exercise these contracts with synthetic inputs. Building and
qualifying the Windows service, user sessions, tray, IPC ACLs, and installer
still requires Windows; a passing Linux test suite does not qualify an installer.
The app-pause implementation also requires native Windows qualification of
multi-thread suspension, permission failures, service interruption/restart,
localized service-account names, and journal replacement under full-disk or
power-loss conditions. Coordination with an external debugger or another tool
that independently suspends the same threads is outside this implementation's
ownership model.
