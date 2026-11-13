# Notifications

## Channels

Implemented:
- Dashboard in-app alerts (always recorded)
- Email via parent-configured SMTP
- Webhook — a JSON `POST` to a parent-supplied generic receiver. The body uses
  (`title`, `message`, `priority`, `severity`, `device`, `time`).

Native **ntfy** and **Gotify** adapters are not implemented or qualified. Their
payload, authentication, and priority contracts need a provider-specific adapter
or a parent-managed compatible receiver; accepting JSON alone does not establish
compatibility.

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
| Critical | Immediate via all enabled channels |
| High | Immediate via all enabled channels |
| Medium | Dashboard; included in the next enabled daily digest |
| Low | Dashboard; included in the next enabled daily digest |

The saved **Immediate minimum severity** selects Low, Medium, High (default), or
Critical. A finding first has to qualify under its child's alert policy. A
category set to Monitor stays in the feed without immediate delivery; Allow
remains suppressed. Lowering the immediate threshold does not lower the child's
alert-creation threshold or retroactively notify on historical alerts.

Protected categories (self-harm, grooming, threats, sexual exploitation,
child sexual content, and parent watch phrases) retain the existing safety
floor: High and Critical findings qualify for immediate delivery even when the
ordinary threshold is Critical. Their lower-severity findings use the selected
notification threshold. The global notifications switch and notification consent
still gate automatic alert and digest delivery. The explicit parent-triggered
synthetic configuration test is a separate operation. No alert automatically executes an app pause
or other enforcement action.

Queue creation and each external channel evaluate current policy. Settings and
profile policy are refreshed again after SMTP, before a subsequent webhook, so
a parent change during the first transport can stop the second. Raising the threshold
or changing a category to Monitor/Allow suppresses a pending ordinary alert at
its next attempt. Suppression is visible as a skipped job with reason
`current_policy`; channels already delivered cannot be recalled. Retry attempts
do not resend a channel whose success is already recorded. The alert's Notify
action follows the same rules and reports a conflict if the alert is ineligible.
Synthetic channel tests are independent of alert severity.

## SMTP configuration

Dashboard **Settings → Notifications**:
- Server host + port
- Username + password (encrypted at rest with the master key)
- TLS mode (STARTTLS / SSL / none)
- "From" address
- Webhook URL (optional)
- Private/internal webhook opt-in for LAN, loopback, or self-hosted endpoints
- Test button — sends a synthetic test to **every configured channel** and records a
  per-channel result in the audit log. Built-in transports reduce exceptions to
  fixed failure categories and HTTP status codes; they do not return raw server
  exception messages. This keeps potentially echoed credentials or token-bearing
  request URLs out of those error details and application warnings.

## Daily digest

The notification worker creates one digest record per family-local calendar day
after the configured local time, covering the previous complete day. Scheduling uses the configured IANA timezone
and handles daylight-saving transitions. The digest is metadata-only: counts,
severity, category labels, profile identifier, alert identifier, and timestamps.
It excludes screenshots, extracted text, summaries, URLs, window titles, and app
names. Each run is durable and idempotent and records its result for audit and
diagnostics. The immediate threshold does not change this separate digest
schedule. All retained alerts in the selected day contribute to the counts.
The worker rechecks notification and digest enablement between digest channels.
Delivery retries are at least once around a crash after remote acceptance and
before local success persistence; remote exactly-once delivery is not promised.

## Audit

Per-channel attempts are stored in `notification_logs`; queue outcomes are stored
in `notification_jobs`. The parent-only notification status endpoint shows
bounded metadata without message bodies, transport secrets, or arbitrary error
strings. Configuration changes and synthetic channel tests also create audit
entries. The Audit page supports retained-history pagination and metadata search;
notification delivery diagnostics remain in Settings.
