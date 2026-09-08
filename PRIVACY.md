# Privacy

GuardianNode's privacy model is local-first: there is no GuardianNode cloud by
default, data stays on a parent-owned machine or home server, and parents/admins
control access, retention, deletion, and export.

GuardianNode is still monitoring software. Screenshots and OCR output may
include sensitive content visible on the child's screen. Parents should configure
capture scope, retention, and access carefully.

## What GuardianNode Processes

- Screenshots from the configured Windows session
- OCR text extracted from screenshots
- Vision model analysis of screenshots/images
- App/window names and URLs visible in captured screenshot context where available
- Risk results, categories, summaries, and confidence scores
- Parent/admin actions such as evidence views, exports, wipes, and pauses

Current installer defaults enable visible desktop screenshot capture. Depending
on policy/settings, a deployment may capture the full visible screen or only
capture when configured apps are active. Assume captured evidence can contain
private messages, names, addresses, school information, payment pages, health
information, or other sensitive on-screen material.

## What GuardianNode Does Not Do

- It does not perform raw system-wide keylogging.
- It does not secretly install itself.
- It does not send child data to a GuardianNode-operated cloud.
- It does not require a cloud account or subscription.
- It does not bundle model weights.
- It cannot detect every risk.

## Where Data Goes

- **All-in-one mode:** backend, dashboard, agent, Ollama, database, evidence, and
  keys stay on one machine.
- **Separated mode:** child-device events travel from the Windows agent to a
  parent-owned backend on the local network or VPN.
- **Ollama:** model inference happens on the local/user-configured Ollama
  endpoint.
- **Notifications:** SMTP/webhooks are sent only if the parent configures them.

Fresh installations use a GuardianNode family certificate authority and HTTPS.
The parent transfers a short-lived `.gnpair` bundle containing the CA certificate,
exact server URL, expiry, and fingerprint to the child installer. The agent pins
that CA and refuses a different HTTPS issuer or server URL. Loopback HTTP remains
available only for explicit source-development workflows. Built-in TLS does not
make public internet exposure supported; keep the server on a family LAN or VPN.
See [docs/SECURE_LAN_SETUP.md](docs/SECURE_LAN_SETUP.md).

## Consent And Optional External Processing

Monitoring stays gated until a parent records the current privacy choices and
acknowledges showing the child-facing notice. The parent can later withdraw
consent while retaining existing evidence through its normal retention window,
or withdraw and queue the evidence for deletion. Device credentials are revoked
in either case.

External AI review is off by default. Enabling the privacy choice alone never
sends evidence: every review also requires an exact minimized preview and a
separate parent confirmation. Local rules and local Ollama processing do not
depend on this optional feature.

Use the [child monitoring notice](docs/CHILD_MONITORING_NOTICE.md) as a starting
point for the required family conversation. The
[data-destination inventory](docs/VENDOR_INVENTORY.md) describes every built-in
local and optional external disclosure path.

## Evidence Storage

GuardianNode encrypts retained screenshot blobs and collected event text with
AES-256-GCM. On new Windows installations, the 32-byte backend master key is
wrapped with Windows DPAPI in LocalMachine scope and stored as
`keys/master.key.dpapi`. On Linux, macOS, and source deployments outside
Windows, the current alpha stores `keys/master.key` with restrictive filesystem
permissions. Upgraded Windows installations may retain a legacy raw key after
generating a DPAPI-wrapped copy; verify a portable backup before removing the
legacy file. DPAPI LocalMachine protects against casual file copying but is not
a boundary against a sufficiently privileged process on that machine.

Create a portable, passphrase-encrypted key backup from the backend environment:

```bash
cd backend
python -m app.services.encryption export-key-backup /safe/path/guardiannode-master-key-backup.json
```

Restore it when moving or recovering the backend:

```bash
cd backend
python -m app.services.encryption import-key-backup /safe/path/guardiannode-master-key-backup.json
```

The 12-word recovery code resets the parent dashboard account only. It cannot
decrypt evidence and does not replace a master-key backup.

## At-Rest Encryption Boundary

| Data | Current alpha storage |
|---|---|
| Retained screenshot/evidence bytes | AES-GCM encrypted |
| Collected OCR/event text in `Event.redacted_text_enc` | AES-GCM encrypted |
| Completed `.gnexport` package | Encrypted with the backend master key |
| App name, window title, URL, timestamps, device/profile IDs | Plaintext database metadata |
| Child profile name, notes, age group, custom watch phrases | Plaintext database fields |
| Risk summary, category list, evidence snippets, confidence | Plaintext database fields |
| Alert notes/actions and notification summaries | Plaintext database fields |
| Audit details and source IP | Plaintext database fields |
| Pending screenshot image | Encrypted |
| Pending screenshot JSON metadata | Plaintext in the protected backend data directory |

GuardianNode does not encrypt the whole SQLite database in this alpha; the
table above identifies plaintext metadata explicitly. Use
full-disk encryption on the backend host. Anyone with privileged access to the
live backend process, database, key material, or unlocked operating system may
access GuardianNode data.

## Redaction And Filtering

GuardianNode may apply basic text filtering/redaction in some collectors and
backend paths, but this is best-effort. Parents should assume captured evidence
can contain sensitive on-screen information.

The primary privacy protections are local-first storage, parent-controlled
access, configurable retention/deletion, and no vendor cloud by default.

## Retention And Deletion

Parents/admins control retention and deletion in the dashboard. Wipes remove
database rows and encrypted evidence files from GuardianNode's storage. If a
file operation fails, GuardianNode preserves a visible retry record instead of
claiming deletion succeeded; pending-deletion evidence is excluded from new
archives. As with any application, deleted disk sectors may still be recoverable
by forensic tools depending on the filesystem and storage hardware.

## Sharing Data

Do not upload real child screenshots, private messages, evidence exports, device
tokens, pairing codes, or logs containing personal information to public GitHub
issues or discussions.

For non-sensitive privacy/support questions, use GitHub Issues or Discussions.
For security-sensitive reports, follow [SECURITY.md](SECURITY.md).

If you share evidence with a school, counselor, therapist, platform, or law
enforcement agency, that decision is yours. GuardianNode does not auto-report to
third parties.
