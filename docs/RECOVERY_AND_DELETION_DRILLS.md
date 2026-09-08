# Recovery and Deletion Drills

Run both drills on the exact release candidate with synthetic data. Never use a
family's production evidence as a test fixture. Store raw logs and secrets
outside git; commit only scrubbed summaries under `docs/release-validation/`.

## Backup and restore drill

1. Record commit, artifact hashes, OS, deployment mode, database schema, and
   UTC start time.
2. Create synthetic profiles, paired devices, alerts, evidence, consent,
   requests, settings, and audit records. Record counts and hashes.
3. Export a passphrase-protected master-key backup and the authenticated archive
   using the documented tools. Store the passphrase separately.
4. Restore into an isolated clean target pre-enrolled with the expected archive
   trust identity. Do not restore into the source instance.
5. Confirm archive signature/identity, format, aggregate size, compression
   ratio, frame/time budgets, and path checks are enforced. Tamper with one copy
   and prove it is rejected.
6. Confirm restored hooks, sessions, credentials, and integrations remain
   quarantined/inactive.
7. Verify expected database counts and hashes, decrypt retained synthetic
   evidence, sign in with a newly established session, and run readiness.
8. Re-pair a synthetic device rather than trusting copied endpoint identity.
9. Record rollback behavior and securely destroy the isolated drill data.

Pass only if the good archive restores completely, the tampered archive fails
closed, active configuration stays quarantined, and no secret appears in logs.

## Deletion drill

1. Create synthetic evidence with known plaintext and ciphertext hashes.
2. Exercise a single-evidence deletion, retention expiry, consent
   withdraw-and-delete, and whole-profile/family deletion where supported.
3. Verify the UI/API exposes “pending” or “failed” until the encrypted file is
   actually removed. Force one unlink failure and confirm durable retry state,
   retry count, and operator visibility.
4. Confirm pending-deletion blobs are excluded from export/archive and cannot be
   revealed or downloaded.
5. Remove the fault, run the retry worker, and verify file removal before the
   database record is finalized.
6. Check database rows, evidence directories, queues, backups covered by the
   retention policy, notification payloads, and audit logs. Audit records may
   retain non-content proof of the deletion action.
7. Search logs and temporary directories for the known synthetic marker.

Pass only when promised content is gone from every in-scope live location,
failures are truthful and retryable, and any backup exception is disclosed with
its expiry.

## Scrubbed evidence template

```text
Drill:
Commit and artifact SHA-256:
Deployment/OS:
UTC start/end:
Operator/reviewer roles:
Synthetic fixture ID:
Expected result:
Observed result:
Faults injected:
Secret/log scan result:
Residual data and documented reason:
Pass/fail and blocker owner:
Evidence location (restricted, outside git):
```
