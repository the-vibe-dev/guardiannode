# Build Week Judge Troubleshooting

## Guardian Review says setup required

- Confirm `GUARDIANNODE_GUARDIAN_REVIEW_ENABLED=true` in the backend service
  environment and restart the backend.
- For the no-key judge path, select provider `mock` and enable demo mode.
- For live mode, confirm the key is in the server environment—not the browser—
  and that the explicit ZDR confirmation matches verified account controls.
- `codex` deliberately reports unavailable in this candidate; use mock or the
  advanced direct Responses API path.

## Missing or invalid API key

The incident remains local and usable. Guardian Review stores a sanitized
failure and does not delete the alert. Correct the backend secret and request a
fresh assessment. Never paste keys into screenshots, issues, logs, or demo
recordings.

## Timeout, rate limit, or network outage

The request is durable. Leave the page or refresh; history continues to show
queued/running/failed state. Only eligible transient failures are retried, with
bounded attempts. Local detection and the dashboard remain available.

## Duplicate click or browser refresh

Consent is bound to the preview digest and idempotency identity. A duplicate
submission returns the existing review. A deliberate fresh assessment must be
requested explicitly.

## Backend restart or database lock

Restart the service after releasing the lock. A queued/running review is
recoverable from local state; the original incident is independent of the
external result. Check free disk space and use `/api/health/ready` before retrying.

## Agent disconnected

Existing incidents and demo scenarios remain reviewable. Check the Devices page,
Windows service status, configured backend URL, trusted firewall/VPN path, and
pairing state. Do not expose the backend directly to the public internet.

## Corrupt incident or invalid model output

Guardian Review fails safely with a controlled error and preserves the incident.
Malformed output is never rendered as an assessment and is not blindly retried.
Use the local incident evidence and, for demo recovery, reset and trigger a new
synthetic scenario.

## Port conflict or stale process

The backend defaults to loopback port 8787. Stop the old GuardianNode service or
change the configured port consistently. Do not terminate unrelated processes.
Verify the dashboard and agent use the same trusted backend address.

## Uninstall and reinstall

Export a portable encryption-key backup and database backup first. Record
whether the installer preserves or removes the data directory. A reinstall must
not silently replace keys for existing encrypted evidence. See the clean-install
checklist before release promotion.
