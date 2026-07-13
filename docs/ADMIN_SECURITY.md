# Administrative security

GuardianNode uses a signed, HTTP-only browser session and requires password
step-up verification before sensitive administrative changes. Ordinary
sensitive actions use a 15-minute verification window. Key, backup, transport,
and update configuration use a five-minute critical window.

The API returns a structured `step_up_required` challenge containing the level,
method, and attempted action. The dashboard asks for the password and retries
the original request only after `/api/auth/reauth` succeeds. API clients must
follow the same flow; possession of an unattended browser cookie is not enough.

Step-up currently protects notification destinations, retention changes,
policy changes, device enrollment and revocation, archive operations, and
backup configuration. Every denied challenge and successful reauthentication
is written to the audit log with actor, action, source address, and target path.

Changing the administrator password or using account recovery revokes all
existing browser sessions and clears every step-up grant. GuardianNode's closed
beta retains one administrator account; parent/viewer accounts, passkeys, and
MFA are not yet supported.
