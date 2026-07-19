# Guardian Review Configuration

Guardian Review is disabled by default. The Windows agent, local detectors,
incident storage, and dashboard continue to work without any cloud provider.
Never commit a real API key or paste one into the browser.

## Judge-friendly mock mode

Add these values to the backend service environment, then restart it:

```dotenv
GUARDIANNODE_GUARDIAN_REVIEW_ENABLED=true
GUARDIANNODE_GUARDIAN_REVIEW_PROVIDER=mock
GUARDIANNODE_DEMO_MODE_ENABLED=true
```

Mock mode is deterministic, local, and synthetic-only. It requires no network
request and no API key. Sign in to the dashboard and open **Synthetic demo**.

## Live OpenAI Responses API mode

Use a backend-only secret source appropriate to the installation:

```dotenv
GUARDIANNODE_GUARDIAN_REVIEW_ENABLED=true
GUARDIANNODE_GUARDIAN_REVIEW_PROVIDER=openai
GUARDIANNODE_GUARDIAN_REVIEW_MODEL=gpt-5.6
GUARDIANNODE_GUARDIAN_REVIEW_ZDR_CONFIRMED=true
GUARDIANNODE_OPENAI_API_KEY=replace-in-local-secret-store
```

Set `GUARDIANNODE_GUARDIAN_REVIEW_ZDR_CONFIRMED=true` only after the operator
has verified that the exact OpenAI project used by the service has approved Zero
Data Retention controls. GuardianNode also sends `store: false`, but does not
claim that this flag alone guarantees zero retention. Restart the backend after
secret/configuration changes. The key is never returned by the readiness API.

Optional operational settings:

| Variable | Default | Purpose |
|---|---:|---|
| `GUARDIANNODE_GUARDIAN_REVIEW_TIMEOUT_SECONDS` | `45` | Timeout per external attempt |
| `GUARDIANNODE_GUARDIAN_REVIEW_MAX_ATTEMPTS` | `2` | Total attempts for eligible transient failures |
| `GUARDIANNODE_GUARDIAN_REVIEW_MODEL` | `gpt-5.6` | Requested Responses API model alias |
| `GUARDIANNODE_DEMO_MODE_ENABLED` | `false` | Enables synthetic dashboard scenarios |

Authorization, policy/validation errors, refusals, and malformed structured
output are not blindly retried. Timeouts, rate limits, and eligible temporary
service failures use bounded retry behavior.

## Coding-agent provider

`GUARDIANNODE_GUARDIAN_REVIEW_PROVIDER=codex` is intentionally fail-closed in
this release. The dashboard reports a security hold because Codex is a coding
agent with local tools. Re-enabling a parent-friendly subscription flow requires
an enforceable zero-tool, minimal-environment runtime contract.

## Synthetic CLI harness

From the backend environment:

```bash
python -m app.guardian_review_harness --provider mock --scenario unknown-contact
python -m app.guardian_review_evaluation --provider mock
```

Both commands emit machine-readable JSON and use repository synthetic fixtures.
The live evaluation command requires both `--confirm-live` and `--confirm-zdr`.
