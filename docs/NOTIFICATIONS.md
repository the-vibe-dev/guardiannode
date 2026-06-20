# Notifications

## Channels

Implemented:
- Dashboard in-app alerts (always recorded)
- Email via parent-configured SMTP
- Webhook — a JSON `POST` to a parent-supplied URL, compatible with self-hosted/local
  push services such as **ntfy** and **Gotify** (both accept a JSON body) as well as
  generic webhook receivers. The body uses common field names
  (`title`, `message`, `priority`, `severity`, `device`, `time`).

Later:
- Windows toast on parent's PC (separated mode)

Privacy note: all channels are parent-controlled. GuardianNode does not route
notifications through a GuardianNode vendor cloud, but alert summaries leave the
local server if the parent configures an external SMTP host or webhook service.
Webhook URLs that target private/internal addresses are blocked by default and
require the explicit private/internal opt-in in Settings.

## Severity routing

| Severity | Default behavior |
|---|---|
| Critical | Immediate via all enabled channels; optional enforcement |
| High | Immediate via all enabled channels |
| Medium | Bundled into daily digest unless repeated |
| Low | Dashboard only |

## SMTP configuration

Dashboard **Settings → Notifications**:
- Server host + port
- Username + password (encrypted at rest with the master key)
- TLS mode (STARTTLS / SSL / none)
- "From" address
- Webhook URL (optional)
- Private/internal webhook opt-in for LAN, loopback, or self-hosted endpoints
- Test button — sends a synthetic test to **every configured channel** and records a
  per-channel result in the audit log. Test results never include the SMTP password
  or any secret, only the transport-level outcome.

## Daily digest

Sent at parent-configured time (default 8 AM local). Includes:
- Critical/high alerts since last digest
- Medium alert count
- New devices online
- Service health status

## Audit

Every notification dispatched gets an `audit_logs` row with channel, severity, alert_id, and delivery result.
