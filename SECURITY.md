# Security Policy

GuardianNode is alpha/developer-preview software for local family deployments.
It is designed for parents or guardians monitoring child devices they own or
administer. It is not designed for public internet exposure, stealth deployment,
employee surveillance, raw keylogging, or credential collection.

## Supported Versions

Only the latest tagged alpha release receives security fixes. Builds from
`main` are best-effort developer snapshots.

| Version | Supported |
|---|---|
| Latest tagged alpha | Yes |
| `main` branch builds | Best-effort |
| Older pre-alpha commits | No |

## Threat Model

GuardianNode assumes:

- A parent/admin controls the backend machine and dashboard credentials.
- The child-device agent runs on a Windows device the parent is allowed to
  administer.
- The deployment is all-in-one, on a trusted home LAN, or behind a trusted VPN or
  reverse proxy.
- The backend is not exposed directly to the public internet.

Security boundaries:

- Parent dashboard access requires admin authentication.
- Child devices authenticate to ingest APIs with device credentials after
  pairing.
- Retained screenshot blobs and collected event text are encrypted at rest with
  AES-256-GCM using the backend master key.
- The backend data directory, key directory, and host OS remain trusted.

Important limitations:

- Separated mode currently uses local-network HTTP unless the operator adds TLS,
  a VPN such as Tailscale/WireGuard, or a trusted reverse proxy.
- GuardianNode does not encrypt the whole SQLite database in this alpha. App
  names, window titles, URLs, timestamps, device/profile IDs, child profile
  fields, risk summaries, snippets, alert notes, audit details, and source IPs
  remain plaintext metadata in the database or protected backend data directory.
- On new Windows installs the backend master key is wrapped with Windows DPAPI
  LocalMachine as `keys/master.key.dpapi`. Linux, macOS, and source deployments
  outside Windows currently use `keys/master.key` with restrictive filesystem
  permissions. Upgraded Windows installs may retain a legacy raw key after
  generating a DPAPI-wrapped copy.
- The recovery code resets dashboard access only. It does not derive,
  reconstruct, wrap, or back up the evidence encryption key.
- A determined local Windows administrator can eventually disable or remove any
  user-space monitoring software.
- Classifier output is not a security boundary and may be wrong.

## Evidence Encryption And Recovery

GuardianNode encrypts retained screenshot blobs and collected event text with
AES-256-GCM. On new Windows installations, the 32-byte backend master key is
wrapped with Windows DPAPI in LocalMachine scope and stored as
`keys/master.key.dpapi`. On Linux, macOS, and source deployments outside
Windows, the current alpha stores `keys/master.key` with restrictive filesystem
permissions. Upgraded Windows installations may retain a legacy raw key after
generating a DPAPI-wrapped copy; verify a portable backup before removing the
legacy file. DPAPI LocalMachine protects against casual file copying but is not
a boundary against a sufficiently privileged process on that machine.

Create and store a portable key backup separately from the database and evidence
directory:

```bash
cd backend
python -m app.services.encryption export-key-backup /safe/path/guardiannode-master-key-backup.json
```

Restore it when moving or recovering the backend:

```bash
cd backend
python -m app.services.encryption import-key-backup /safe/path/guardiannode-master-key-backup.json
```

The 12-word recovery code is for parent dashboard account recovery. Losing both
the parent password and recovery code can lock you out of the dashboard. Losing
the backend master key can make encrypted evidence unrecoverable even if the
dashboard password is reset.

## Responsible Disclosure

Do not open a public GitHub issue for exploitable vulnerabilities or child-data
leaks. Please use GitHub's private vulnerability reporting flow if available:
[Report a vulnerability](https://github.com/the-vibe-dev/guardiannode/security/advisories/new).

If private reporting is unavailable, open a minimal public issue asking for a
private maintainer contact channel. Do not include child screenshots, private
messages, raw evidence, secrets, pairing codes, or logs containing personal
information in public issues.

Include in private reports:

- A description of the issue and its impact
- Steps to reproduce using synthetic data when possible
- Version, OS, and deployment shape
- Whether the backend was exposed beyond localhost/trusted LAN/VPN
- Whether you have shared the issue elsewhere

## Unsupported Uses

The maintainers do not support and do not want contributions that enable:

- Stealth deployment or hidden monitoring
- Employee surveillance
- Raw system-wide keylogging
- Credential theft or password capture
- Public internet exposure without hardening
- Cloud telemetry by default
- Attempts to evade operating-system security controls

## Operational Guidance

- Prefer all-in-one mode for early alpha testing.
- For separated mode, use a trusted LAN or VPN and do not port-forward the
  backend to the internet.
- Set a strong parent password and store the recovery code offline.
- Back up the backend data directory and create a portable master-key backup if
  you need evidence recovery.
- Use full-disk encryption on the backend host.
- Use standard, non-admin Windows accounts for children where possible.
- Review [docs/SECURE_LAN_SETUP.md](docs/SECURE_LAN_SETUP.md) before remote
  access.
