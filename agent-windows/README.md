# GuardianNode Windows Agent

Runs a visible capture process in each active Windows user session, with a
SYSTEM broker that owns enrollment credentials, encrypted queue storage,
backend transport, and capture-policy synchronization. The backend performs screenshot
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
- `src/window_tracker.py` — one foreground-window/process snapshot and focus checks
- `src/display_coordinates.py` — temporary per-monitor DPI context for physical pixel bounds
- `src/screenshot_capture.py` — mss-based capture
- `src/ocr_engine.py` — optional local OCR helpers
- `src/broker_service.py` — credentialed Windows broker and parent-policy cache
- `src/broker_client.py` / `src/broker_protocol.py` — bounded local capture/status IPC
- `src/durable_queue.py` — encrypted SQLite screenshot queue for backend outages
- `src/backend_client.py` — HTTP client to backend
- `src/tray_app.py` — tray icon + pause UX
- `src/watchdog.py` — keeps the visible tray running in active sessions
- `src/legacy_recovery.py` — release-only cleanup of restrictions from older builds
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
An authenticated-decryption or payload-decoding failure retires only the unreadable
row and lets healthy queued frames continue. Storage/permission failures preserve
pending rows for recovery; discarded evidence contents are never logged.

## Screenshot capture and review

The endpoint collects visible screenshots for the backend's OCR and AI review.
It does not enforce app usage budgets, impose screen-time limits, suspend apps,
block websites, or display remote intervention prompts. The tray provides visible
monitoring status and parent-dashboard shortcuts; exception and more-time requests
are no longer part of the product.

Monitoring pauses affect screenshot collection only. They do not restrict the
child's ability to use the computer. Consent, capture scope, and retention controls
remain effective. An old `enforcement_enabled: true` configuration is ignored and
cannot restore the removed restriction commands.

Change detection considers the active-window region and the wider primary-display
image. The first permitted frame after a monitoring pause, consent change, or
capture-scope change is eligible immediately. Deduplication remembers only frames
accepted by the local capture sink; a failed broker submission does not suppress
the next identical frame. The broker must explicitly acknowledge `queued` before
the session agent treats a screenshot as admitted.

Primary-display selection uses the display's primary flag when available and never
falls back to capturing the combined desktop. Window bounds and capture use physical
pixels in a temporary per-monitor Windows DPI context. Window identity and process
are sampled from the same foreground handle and checked again after capture. A
changed foreground discards an app-scoped frame; primary-display frames omit stale
or other-display app/title metadata. App-scoped frames are clipped to the visible
desktop, including negative desktop coordinates. This mode captures a visible
rectangle, so an overlapping window can still appear in its pixels.

Display identity or capture-bound changes reset deduplication. Explicit zero change
thresholds are honored, and maximum-interval refresh uses monotonic elapsed time so
a clock correction cannot postpone it. JPEG encoding keeps the highest fitting
quality under the existing broker transport bound; high-entropy frames no longer
fail admission solely because the initial JPEG is too large.

Primary-display capture remains the default. Other monitors, secure desktops, and
unobserved user sessions must not be described as covered. Periodic captures and
perceptual hashing can miss brief or small visual changes. The maximum interval
refresh helps reduce that gap but is not a guarantee of complete capture.
Portable image/API tests cover these paths with synthetic displays. Native Windows
mixed-DPI displays, monitor hot-plugging, RDP, and focus transitions still require
qualification on supported Windows hardware.

## Upgrading an older build with active restrictions

The broker runs a release-only recovery pass at the beginning of its normal
control loop, including before pairing credentials are available. This pass retires
old app-pause leases immediately, regardless of their former expiry. It never
creates a new lease, discovers a new process to suspend, or reapplies a restriction.

A known process is resumed only when its PID, creation time, and Windows-normalized
executable still match the protected journal. Recycled PIDs and changed executable
identities are discarded without a process operation. Failed releases retain their
identities for retry after restart. Critical system processes, recognized service
accounts, and GuardianNode processes remain protected. Very old journals containing
only numeric PIDs are preserved as unverified; they require operator recovery with
an independently verified identity or a managed device restart.

Domain recovery removes only exact loopback hosts lines in the former GuardianNode
format. It also handles orphaned owned lines left by an old interruption between
writing hosts and committing the journal. Other lines retain their original bytes.
A detected concurrent file edit aborts replacement and retries on a later poll.
Permission or disk failures remain reported as incomplete recovery. An unreadable
or corrupt journal is preserved and does not stop consent-policy polling.

Historical parent Undo commands are accepted only as compatibility recovery. New
app pauses, domain blocks, remote prompts, and unknown commands are rejected at
both the broker dispatch boundary and the recovery executor. Normal screenshot
review creates none of those commands.

Portable tests use synthetic processes and temporary files. Windows service,
thread resume behavior, protected storage ACLs, hosts replacement, tray sessions,
IPC, and installer upgrades still require native Windows qualification. Do not
delete an unresolved recovery journal to dismiss a recovery error.
