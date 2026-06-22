# GuardianNode Threat Model

This document describes what GuardianNode protects, who it protects against, and
the privacy/security trade-offs we have deliberately made. It is written to be
read by parents, security reviewers, and contributors. GuardianNode is a
local-first, open-source child-safety tool; transparency about its risks is a
product feature, not an afterthought.

Related reading: [PRIVACY.md](https://github.com/the-vibe-dev/guardiannode/blob/main/PRIVACY.md), [SECURITY.md](https://github.com/the-vibe-dev/guardiannode/blob/main/SECURITY.md),
[SAFETY_BOUNDARIES.md](SAFETY_BOUNDARIES.md), [REDACTION.md](REDACTION.md),
[ARCHITECTURE.md](ARCHITECTURE.md).

## 1. What we are protecting

| Asset | Why it matters |
|---|---|
| Captured evidence (screenshots, extracted text) | Reveals a child's private activity; high-sensitivity. |
| The parent's master key / login | Decrypts all evidence; full account compromise if leaked. |
| SMTP / webhook credentials | Could be abused to send mail or hit internal services. |
| Audit log integrity | The accountability record for who viewed what. |
| Classifier prompts/rules | Determine what is flagged; tampering creates blind spots. |

## 2. Trust boundaries

```
[Child PC] agent ──HTTP on trusted LAN/VPN/TLS──> [Local backend] <──cookie auth── [Parent browser]
 (screenshots + OCR text)            │
                                     ├─ encrypted evidence at rest (master key)
                                     └─ Ollama vision/text inference (LAN, no SaaS)
```

- **Agent -> backend**: device-token authenticated. The agent reviews visible
  screen content from the configured Windows session. Runs on loopback, a
  trusted family LAN, or a VPN/reverse proxy. No GuardianNode cloud is in the
  path by default.
- **Parent → backend**: cookie-based session after password login; recovery code
  for reset.
- **Backend → inference (Ollama)**: LAN endpoints the operator controls. No model
  call leaves the operator's network by default.

## 3. Adversaries and what we do about them

### 3.1 A curious or motivated child (on the monitored device)
- **Monitoring interruption.** Mitigation: agent runs as a scheduled task; the
  backend tracks `last_seen` and surfaces offline/heartbeat gaps to the parent. We
  do **not** hide the agent — GuardianNode is visible monitoring by design (a tray
  icon and clear install footprint), not stealthware.
- **Local pause abuse.** Qualified Windows installer builds are moving pause
  authority into the GuardianNode broker service. Legacy/source fallback paths
  may still read a local `paused_until` marker, so ordinary-family installer
  release remains blocked until clean Windows tests prove the child account
  cannot alter pause state directly.

### 3.2 Network attacker on the LAN
- **Sniff agent->backend traffic.** Mitigation: use all-in-one mode, a trusted
  LAN, VPN, or reverse-proxy TLS. Evidence is encrypted at rest regardless. mDNS
  advertising can be disabled.
- **Reach the backend ingest API.** Ingest is device-token authenticated; in
  all-in-one mode the backend binds `127.0.0.1` only.

### 3.3 Attacker who steals the backend disk / database
- **Read evidence directly.** Mitigation: evidence blobs and redacted text are
  encrypted at rest with AES-256-GCM. New Windows backend keys are wrapped with
  DPAPI LocalMachine as `<data>/keys/master.key.dpapi`. Linux, macOS, and source
  deployments outside Windows use a raw `<data>/keys/master.key` protected by
  filesystem permissions only. Upgraded Windows alpha installs may retain a
  legacy raw key after generating a DPAPI-wrapped copy; verify a portable
  backup before removing the legacy file. An attacker with full machine access
  while the backend can decrypt, with the raw key directory, or with sufficient
  Windows privilege to use the DPAPI-wrapped key can decrypt stored evidence.
  At-rest encryption protects against partial exposure, not total machine
  compromise.
- **Read plaintext metadata.** The current alpha does not encrypt the whole
  SQLite database. App names, window titles, URLs, timestamps, profile fields,
  risk summaries, snippets, alert notes, audit details, and pending screenshot
  JSON metadata remain plaintext metadata in the protected backend data
  directory. Use full-disk encryption on the backend host.
- **Replay old data.** Retention policy and the cleanup worker bound how long
  evidence lives (see [RETENTION.md](RETENTION.md)).

### 3.4 Attacker who compromises the parent's browser/session
- This is full compromise — they can view evidence and change policy. Mitigations
  are conventional: strong parent password, recovery code kept offline, running
  the dashboard only on trusted devices. Every evidence reveal is audit-logged so
  the parent can detect unexpected views.

### 3.5 A malicious or buggy parental-control vendor (i.e. us)
- This is the risk highlighted by the FTC/UCL research linked in the readiness
  plan: parental-control tools are themselves a privacy hazard. Our mitigations
  are structural: open source (auditable), local-first (no default cloud
  telemetry), encrypted evidence, **no raw keylogging**, visible tray/status, and
  parent-controlled capture/retention settings.

## 4. Privacy-preserving design decisions

- **No raw keylogging.** We capture on-screen text in context (via screenshot OCR),
  not every keystroke.
- **Capture scope is parent-controlled.** Current installer defaults enable
  visible desktop capture. Depending on policy/config, deployments may use
  full-screen capture or only capture when configured apps are active.
- **Basic text filtering/redaction is best-effort**, where implemented. Parents
  should assume evidence can contain sensitive on-screen content. See
  [REDACTION.md](REDACTION.md).
- **Evidence stored only when severity ≥ medium**, encrypted, and decrypted only
  on an audit-logged parent view.
- **No stealth mode, no adult monitoring, no default cloud telemetry.** See
  [SAFETY_BOUNDARIES.md](SAFETY_BOUNDARIES.md).

## 5. Known limitations (honest disclosure)

- Capture scope and pause enforcement assume the child account is not a local
  administrator on the monitored PC.
- Custom watch phrases match OCR'd/extracted text, not text rendered inside
  images beyond what the vision model returns.
- Unsigned installers trigger SmartScreen until code signing lands (see
  [installer/shared/SIGNING_PLAN.md](https://github.com/the-vibe-dev/guardiannode/blob/main/installer/shared/SIGNING_PLAN.md)); verify
  downloads against the published `SHA256SUMS`.
- The classifier can produce false positives/negatives; parents have
  false-positive/false-negative feedback controls, and GuardianNode is **not** an
  emergency-response system.

## 6. Reporting

Security issues: see [SECURITY.md](https://github.com/the-vibe-dev/guardiannode/blob/main/SECURITY.md) for the coordinated-disclosure
process.
