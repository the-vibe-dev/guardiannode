# Clean Windows Release-Candidate Checklist

Target artifact version: `0.1.0-alpha.3`

Qualification target: fresh Windows 11 x64 machine or disposable VM

Status: required manual evidence; not satisfied by the developer workstation

Record the machine/VM image, Windows build, artifact SHA-256, tester, date, and
result without including personal data, credentials, private hostnames, or
internal addresses.

## Install and first launch

- [ ] Download artifacts from the candidate release while logged out.
- [ ] Verify `SHA256SUMS.txt` before execution.
- [ ] Record the expected unsigned-installer warning.
- [ ] Install all-in-one mode to the default path.
- [ ] Confirm database/key directories initialize with appropriate ownership.
- [ ] Confirm backend and dashboard start without a developer checkout.
- [ ] Create a synthetic parent test account using the local one-time setup token.
- [ ] Confirm the setup/bootstrap token value is absent from application logs.

## Agent and golden path

- [ ] Start/enroll the Windows agent and confirm visible tray/status behavior.
- [ ] Confirm device health and local classifier/model readiness.
- [ ] Enable mock Guardian Review and synthetic demo mode.
- [ ] Trigger a scenario and verify local incident persistence/display.
- [ ] Preview redaction, remove optional context, cancel, and confirm no send.
- [ ] Repeat, consent, view strict result and communication plan, save feedback.
- [ ] Reset demo and confirm non-demo data is preserved.

## Recovery

- [ ] Missing key and invalid-key failures preserve the incident/dashboard.
- [ ] Simulated network outage, timeout, and rate limit fail safely.
- [ ] Refresh during a request and confirm durable state/history.
- [ ] Double-click submit and confirm one accidental request.
- [ ] Restart backend during queued/running work and verify recovery.
- [ ] Disconnect/reconnect agent without losing existing incidents.
- [ ] Reboot Windows and verify backend/agent restart behavior.
- [ ] Confirm no stale service or port conflict after restart.

## Uninstall and reinstall

- [ ] Export database and portable key backup.
- [ ] Uninstall agent/server and record intentional retained data/residue.
- [ ] Reinstall the same artifact and verify configuration migration.
- [ ] Confirm encrypted historical data remains readable only with preserved keys.
- [ ] Perform a clean-data uninstall/reinstall and confirm first-run behavior.

## Release decision

- [ ] Attach sanitized screenshots/log excerpts and exact checksums to the
      maintainer release record.
- [ ] Mark every failure and workaround; do not convert unchecked items into a
      passing claim.
- [ ] Promote from candidate only after high-impact install/reboot/uninstall
      failures are fixed and the exact artifacts are requalified.
