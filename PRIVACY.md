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
- App/window names and URLs where collectors support them
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

Separated mode currently uses local-network HTTP unless the operator adds TLS,
Tailscale, WireGuard, or a trusted reverse proxy. Do not expose the backend
directly to the public internet. See [docs/SECURE_LAN_SETUP.md](docs/SECURE_LAN_SETUP.md).

## Evidence Storage

Sensitive event fields and evidence blobs are encrypted at rest with AES-GCM
using a local backend `master.key` file. The key is protected by filesystem
permissions and installer-applied ACLs where available. It is not currently
wrapped by DPAPI or another OS keystore.

The 12-word recovery code resets parent dashboard access only. It does not
derive, reconstruct, or back up the evidence encryption key. If `master.key` is
lost, encrypted evidence may not be recoverable.

## Redaction And Filtering

GuardianNode may apply basic text filtering/redaction in some collectors and
backend paths, but this is best-effort. Parents should assume captured evidence
can contain sensitive on-screen information.

The primary privacy protections are local-first storage, parent-controlled
access, configurable retention/deletion, and no vendor cloud by default.

## Retention And Deletion

Parents/admins control retention and deletion in the dashboard. Wipes remove
database rows and encrypted evidence files from GuardianNode's storage. As with
any application, deleted disk sectors may still be recoverable by forensic tools
depending on the filesystem and storage hardware.

## Sharing Data

Do not upload real child screenshots, private messages, evidence exports, device
tokens, pairing codes, or logs containing personal information to public GitHub
issues or discussions.

For non-sensitive privacy/support questions, use GitHub Issues or Discussions.
For security-sensitive reports, follow [SECURITY.md](SECURITY.md).

If you share evidence with a school, counselor, therapist, platform, or law
enforcement agency, that decision is yours. GuardianNode does not auto-report to
third parties.
