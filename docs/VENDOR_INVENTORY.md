# Data Destination and Vendor Inventory

GuardianNode is local-first. This inventory distinguishes runtime disclosure
destinations from build/download dependencies. Operators must review their own
providers, contracts, regions, retention, and credentials before enabling an
integration.

| Destination/component | Default | Data that may be sent | Control and boundary |
|---|---|---|---|
| GuardianNode backend | Required, family-controlled | Screenshots, OCR text, app/window/URL context, device metadata | Pinned HTTPS on loopback/private LAN; encrypted local evidence. |
| Ollama | Local default | Prompt text and optional images needed for configured local classification | Backend-configured local endpoint; do not point at an unreviewed remote host. |
| SMTP server | Off until configured | Alert/digest metadata and recipient address; daily digest excludes screenshots and OCR text | Parent config plus step-up; provider policy governs delivery copies/logs. |
| Webhook destination | Off until configured | Configured alert metadata | Exact HTTPS destination, SSRF controls, no redirects, bounded responses; receiver policy applies. |
| OpenAI Responses API | Off | Only the exact redacted Guardian Review preview approved for that request | Per-use disclosure/confirmation; `store=false`; direct API mode additionally requires operator-confirmed approved ZDR controls. |
| ChatGPT/Codex Guardian Review | Off | Only the exact redacted preview approved for that request | Connected plan/workspace controls apply; no background bulk upload. |
| GitHub | Build/update source only | Repository metadata and release downloads; no child runtime data by design | Verify tag/artifact hashes and signatures. Do not attach family data to issues. |
| Ollama/Tesseract installers and model registries | Install time | Network/download metadata; model files | Privileged Windows downloads require pinned SHA-256 and expected signer where applicable. Review model licenses separately. |

Potential telemetry from the operating system, browser, email provider, VPN,
antivirus, DNS resolver, or reverse proxy is outside GuardianNode's code and
must be included in the deploying family's or pilot operator's inventory.

Before release, record owner, purpose, legal basis/consent, contract or terms,
data categories, retention/deletion behavior, subprocessors, incident contact,
security review date, and disablement test for every enabled non-local
destination. Reconcile this file with locked dependencies and
[third-party notices](https://github.com/the-vibe-dev/guardiannode/blob/main/THIRD_PARTY_NOTICES.md)
on each release candidate.
