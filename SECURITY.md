# Security Policy

## Supported versions

GuardianNode is in **beta**. Only the latest tagged release receives security fixes.

| Version | Supported |
|---|---|
| Latest tagged release | ✅ |
| `main` branch builds | Best-effort |
| Pre-tag commits | ❌ |

## Reporting a vulnerability

**Do not open a public GitHub issue for security bugs.** GuardianNode handles sensitive evidence about children; a published exploit could be used against a vulnerable family before a fix lands.

Please email security disclosures to: `security@guardiannode.example` (replace with the real address before launch).

Include:
- A description of the issue and its impact
- Steps to reproduce, ideally with a minimal proof-of-concept
- The version, OS, and deployment shape (all-in-one vs separated)
- Whether you've shared the issue with anyone else and where

You'll get a reply within **5 business days**. We'll work on a fix and coordinate a disclosure date with you. Once patched, we'll publish a CVE-style advisory in [GitHub Security Advisories](https://github.com/the-vibe-dev/guardiannode/security/advisories).

## Scope

In-scope:
- Authentication/authorization bypass on the backend
- Encryption bypass or key extraction
- Tamper-resistance bypass (e.g. ways for the child to disable monitoring without the parent password)
- Cross-site scripting, CSRF, SQL injection in dashboard or API
- Privilege escalation via the agent service
- Remote code execution
- Information disclosure (especially flagged-event content leaking outside the encrypted store)
- Vulnerabilities in our bundled dependencies that materially affect GuardianNode

Out-of-scope (please don't waste your time):
- Findings against the LLM prompt itself (the local Ollama model is an oracle, not a security boundary)
- Theoretical attacks that require the attacker to already have admin on the machine (we document this as a known limit)
- Issues in third-party services we link to (Ollama, Chrome Web Store, etc.) — report those upstream
- Social engineering of the parent
- Physical access attacks

## Threat model (short version)

**Who we're trying to defend against:**
1. A casual teenager trying to disable monitoring on their own PC
2. A grooming attacker reaching the child via games/chat/email
3. A network-based attacker trying to read evidence from a misconfigured server
4. Accidental data leakage to third parties

**Who we do not claim to fully defend against (yet):**
1. A determined teenager with admin rights and Safe Mode access — this requires the v2 kernel-driver tier
2. A nation-state attacker
3. Anyone with physical access to the encryption key recovery code

See [`installer/shared/tamper_resistance.md`](installer/shared/tamper_resistance.md) for the detailed threat model.

## Encryption key handling

- The master encryption key is generated on first run and shown to the parent once.
- Lost master key = lost evidence. We cannot recover it for you. This is by design.
- The 12-word recovery code uses the BIP39 word list and reconstructs the key deterministically.
- Keep the recovery code physically (paper, safe-deposit box, password manager you trust).

## Dependencies

We use Dependabot/Renovate for automated dependency updates. Critical CVEs in our pinned versions are addressed within 7 days. Run `make audit` to check the current dependency tree.
