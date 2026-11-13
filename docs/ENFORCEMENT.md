# Enforcement

Enforcement is parent-confirmed, narrow, reversible where possible, and never
triggered directly by a classifier result.

## Current actions

- Show a calm child-facing prompt.
- Suspend an exact absolute Windows `.exe` path for 15 minutes, 1 hour, or 24
  hours, with identity-checked release attempts when its last active pause ends.
- Add an exact FQDN to a GuardianNode-owned hosts-file block section.
- Undo only the process/domain state GuardianNode recorded as its own.
- Delete the current alert's evidence through the durable deletion path.

The dashboard first returns the exact command preview. A parent must confirm the
same preview before the backend queues it for the SYSTEM broker. The broker
validates the target again and reports succeeded, failed, or rejected.

App pause records now retain PID, creation time and executable identity before
suspension. Matching relaunches are checked on subsequent broker polls. Multiple
parent pauses share ownership; new Undo commands identify one original pause,
so another active pause can remain in force. Existing external suspensions are
not adopted. This is a reactive exact-path control, not a daily usage budget,
process-creation interception, or category filter.

Known critical OS processes, GuardianNode, the broker/ancestors, and recognized
service accounts are excluded. A partial failure can leave an active bounded
lease and some processes paused. Pending release identities survive restart for
retry; corrupt state is preserved for verified recovery. The exact Windows
service, process and filesystem behavior remains a native release gate.

## v0.4+

- Pi-hole DNS block plugin
- AdGuard Home plugin
- UniFi/UDM plugin
- Home Assistant trigger

## Policy boundary

Profile policy controls capture and alert thresholds. It cannot authorize an
endpoint command. Every endpoint action begins from an authenticated parent on
one alert, passes recent-authentication checks, and uses the two-step exact
preview confirmation.

## Audit

Every enforcement action is logged. The alert's **Action history** shows the
latest commands, stored endpoint receipts, partial outcomes, and Undo. The
**Audit** page supports action/actor/date filters over retained history. See
[Audit and action history](AUDIT_AND_ACTION_HISTORY.md) for receipt semantics,
the API contract, and the legacy journal upgrade procedure.

## Failure modes

- Missing or ambiguous process path → reject without affecting another process.
- Invalid domain or hosts-file conflict → reject and report the failure.
- Child session unavailable → retain/report the command result; do not claim the
  prompt was shown.
- Broker restart during a timed pause → reload full identities and active leases;
  attempt release only after the final matching lease ends.
- Failed release or state persistence → retain recovery information and report
  partial results; a failure does not mean no process is paused.
- Old numeric-PID-only journal → preserve as unverified; undo old active pauses
  before upgrade instead of guessing whether a PID still belongs to that app.
