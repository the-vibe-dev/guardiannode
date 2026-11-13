# Recovery of restrictions from older builds

GuardianNode now focuses on screenshot capture and AI review. New app pauses,
website/domain blocks, child prompts and exception requests are retired. There
is no enforcement switch that restores them in this build.

This page preserves its old path so existing links lead to the upgrade guidance.
It describes release-only compatibility, not an active restriction feature.

## Before upgrading

Use the old version to undo active restrictions and confirm that applications
run and affected domains are accessible. Back up application data, configuration,
keys and the broker's recorded recovery state. Install matching backend,
dashboard and Windows endpoint versions together.

Older numeric-PID-only journals cannot identify a process safely after PID reuse.
Those records stay unverified. Do not guess which current process to resume and
do not delete unresolved state simply to clear an error. A managed restart and
verified operator recovery may be required.

## Recovery-only endpoint

`agent-windows/src/legacy_recovery.py` reads older GuardianNode-owned state. It
releases recorded suspensions only after checking process identity and removes
only the marked hosts entries previously owned by GuardianNode. The broker
retries unresolved recovery through its control loop. The new code cannot
suspend a process, add a blocking hosts entry or display a new child notice.

Malformed or unreadable journals remain available for recovery instead of being
silently discarded. Failed release/persistence remains a failure to resolve;
it does not mean that all old restrictions have disappeared. Native Windows
process, filesystem and service behavior still needs qualification.

## Backend and history

The API rejects new restriction commands and retires exception-request mutations.
Queued legacy restriction commands are rejected rather than delivered as new
work. Historical action receipts and old request data are retained for audit and
compatible reads. Undo for an old action is a separate recovery command; queued
or claimed does not mean recovery has already succeeded.

A stored receipt describes a past execution. It is not continuous live process
telemetry. Later local recovery may resolve a failure without rewriting an older
receipt. An offline old agent cannot learn about these changes until it reconnects
or is upgraded.

## Capture pause is different

Pausing screenshot monitoring controls collection and privacy. It does not lock
the computer, pause a child's app, restrict browsing or allocate usage time.
Consent, retention, evidence deletion and processing safeguards remain active.
