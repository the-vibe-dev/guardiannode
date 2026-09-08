# Incident Response Plan

GuardianNode processes sensitive child and family information. Treat suspected
unauthorized access, disclosure, integrity loss, monitoring bypass, destructive
failure, or unsafe automated behavior as a security/privacy incident.

## Report and triage

Use the private reporting route in
[SECURITY.md](https://github.com/the-vibe-dev/guardiannode/blob/main/SECURITY.md).
Do not include
child screenshots, messages, tokens, archives, or recovery phrases in a public
issue. The incident lead records the UTC time, reporter, affected build and
deployment, scope, current exposure, child-safety urgency, and evidence location.

Severity is based on actual or plausible harm:

- **Critical:** cross-family/public disclosure, active credential or signing-key
  compromise, remote code execution, monitoring continuing after withdrawal,
  or immediate child-safety impact.
- **High:** unauthorized local access to evidence/credentials, systemic
  integrity loss, or widespread failure to surface critical alerts.
- **Medium/low:** contained degradation with no confirmed sensitive disclosure.

## Contain and preserve

1. Put immediate safety first; GuardianNode is not an emergency service.
2. Stop affected distribution and revoke compromised sessions, device tokens,
   API keys, signing identities, or notification secrets as applicable.
3. Isolate—not erase—the affected server/device if forensic evidence matters.
4. Preserve minimal logs, timestamps, configuration, hashes, and versions under
   access control. Do not copy child content unless essential.
5. Disable optional external integrations or network exposure implicated in the
   incident. Keep unaffected local protection running only when safe.

## Investigate, communicate, recover

Identify entry point, affected data and families, dwell time, exploitability,
and whether backups or downstream vendors are involved. Obtain legal/privacy
advice for notification duties and deadlines; do not promise a universal notice
window without jurisdiction-specific review.

Communications must be factual: what happened, what data/actions were affected,
what has been contained, what the family should do, remaining uncertainty, and
where updates will appear. Never expose another family while notifying one.

Recover from a known-good artifact and configuration, rotate trust material,
run readiness plus synthetic capture-to-alert checks, and complete the recovery
and deletion drills when relevant. Require a second reviewer before restoring
distribution.

## Close and learn

Document root cause, timeline, decisions, affected versions, corrective tests,
notification decisions, retained evidence, and owners/dates for follow-ups.
Update the threat model, vendor inventory, runbooks, and release gates. A closed
incident is not evidence that the product is production ready.
