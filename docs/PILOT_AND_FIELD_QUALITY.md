# Controlled Pilot and Field-Quality Protocol

This protocol is a release gate, not evidence that a pilot has occurred. Keep
raw family data outside the repository. Check in only aggregate,
credential-scrubbed results approved for publication.

## Entry criteria

Do not enroll a family until the exact commit has passed source tests and the
target Windows install/reboot/uninstall matrix. Installers must be signed, or
participants must receive a clear unsigned-build warning and verify a published
SHA-256. Legal/privacy review and an incident contact must be in place.

Recruit 10–20 supervised families who explicitly opt in. Avoid presenting the
sample as representative. Record the notice/consent version, monitoring scope,
retention, notification channels, optional external-AI choice, participating
devices, and withdrawal instructions. Give each child the child-facing notice
in age-appropriate language.

## Sampling plan

Create a coverage matrix before enrollment:

| Dimension | Minimum planned coverage |
|---|---|
| Age context | Under 10, 10–13, and 14–17; do not publish tiny identifiable cells. |
| Applications | Browsers, chat, games, office/text, video, and unsupported/problem apps. |
| Display conditions | Light/dark themes, 100–200% scaling, multiple monitors, and common resolutions. |
| Language | English plus each explicitly qualified OCR/classifier language; label all others unsupported. |
| Case type | Clearly safe, clearly concerning, quoted/reported content, jokes, education/health, and ambiguous context. |

Use synthetic fixtures for deliberate danger scenarios. Do not ask children to
create or seek harmful content. Natural-use review should minimize access to raw
evidence and involve only the parent and authorized study staff.

## Measures

For every reviewed sample, record the build, classifier configuration, age
group, app/language bucket, whether capture occurred, model/rule output, parent
assessment, and correction. Report with denominators and confidence intervals:

- Precision/false-positive rate by severity and category.
- Reviewed false negatives from the predeclared sampling method.
- Severity calibration: observed concern rate within each predicted band.
- Capture, OCR, classification, notification, and parent-review latency.
- Monitoring gaps: offline, paused, throttled, backlogged, unsupported app,
  unreadable OCR, or model unavailable.
- Parent corrections, reversals, and unresolved ambiguous cases.
- Child/parent usability reports, including whether notices and controls were
  understood.

Do not collapse “not reviewed” into “correct,” infer universal accuracy from a
small pilot, or publish private examples without separate informed permission.

## Stop conditions

Pause new enrollment and triage immediately for any of these:

- Undisclosed cloud transfer, credential exposure, cross-family access, or
  plaintext non-loopback child traffic.
- Deleted evidence remaining parent-visible without a surfaced retry state.
- Capture continuing through a confirmed pause or consent withdrawal.
- A critical alert that repeatedly fails to reach the configured parent route.
- Sustained backend overload that starves another child's events.
- Serious child distress, coercion, or family use inconsistent with the notice.
- A security incident or legal/privacy concern requiring notification.

Define numerical accuracy and reliability thresholds with the pilot's legal,
safety, and research reviewers before looking at outcomes. Never lower them
afterward merely to pass a release.

## Evidence record

Store the following outside git: participant codes, signed/recorded consent,
raw annotations, incident notes, and any screenshots or message text. A
publishable aggregate report should state commit and artifact hashes, dates,
sample/denominators, exclusions, missing data, configuration, thresholds,
results, corrections, incidents, withdrawals, and the promotion decision.
