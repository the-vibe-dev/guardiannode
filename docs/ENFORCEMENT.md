# Enforcement

Enforcement is parent-confirmed, narrow, reversible where possible, and never
triggered directly by a classifier result.

## Current actions

- Show a calm child-facing prompt.
- Suspend an exact absolute Windows `.exe` path for 15 minutes, 1 hour, or 24
  hours, then resume it automatically.
- Add an exact FQDN to a GuardianNode-owned hosts-file block section.
- Undo only the process/domain state GuardianNode recorded as its own.
- Delete the current alert's evidence through the durable deletion path.

The dashboard first returns the exact command preview. A parent must confirm the
same preview before the backend queues it for the SYSTEM broker. The broker
validates the target again and reports succeeded, failed, or rejected.

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

Every enforcement action is logged. Dashboard **Audit → Enforcement** shows the action history with timestamp, trigger alert, action taken, and result.

## Failure modes

- Missing or ambiguous process path → reject without affecting another process.
- Invalid domain or hosts-file conflict → reject and report the failure.
- Child session unavailable → retain/report the command result; do not claim the
  prompt was shown.
- Broker restart during a timed pause → reload owned state and resume at expiry.
