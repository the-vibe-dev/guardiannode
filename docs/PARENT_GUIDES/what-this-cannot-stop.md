# Understanding screenshot coverage

GuardianNode captures permitted visible screen content and helps a parent review
it. It does not stop websites or apps, impose screen-time limits, or intercept a
conversation before it happens. Its value is understandable evidence and timely
review, with clear reporting of what did and did not run.

## What can be missed

- Screens on another device or a secondary display. Current desktop capture
  covers the primary monitor.
- Content that appears and disappears between screenshot samples, is hidden
  behind another window, or is on a protected/secure desktop.
- Small, compressed, stylized or unsupported-language text that OCR or a model
  cannot read reliably.
- Context outside a captured frame, including a longer conversation or benign
  explanation for alarming wording.
- New or ambiguous patterns that the configured rules and local model miss.
- Periods when capture is paused, consent is off, the endpoint is disconnected,
  or the queue/model is unavailable. An outage may outlast bounded local storage.

A VPN does not inherently hide pixels already visible to the local capture
process. It can affect the agent's connection to your backend. GuardianNode does
not provide a network filtering integration.

## What the dashboard tells you

Check each device's capture receipt and processing state. A heartbeat is only a
connectivity signal. A receipt means the server accepted a screenshot; it does
not mean AI completed. Rules-only or degraded review is reduced coverage. A
missing/stale status is unknown, not evidence that activity was safe.

No alert is not proof of no risk. A flagged screenshot is also not proof of a
person's intent. Review the evidence and context, and record useful/false-positive
feedback so that you can assess noise over time.

## A practical routine

Check capture/review status, review relevant alerts, and talk with your child
about concerning context. Use screenshot monitoring transparently and configure
capture scope and retention deliberately. If there is an immediate concern,
respond directly rather than waiting for an automated alert.
