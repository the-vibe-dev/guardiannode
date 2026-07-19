# Guardian Review Evaluation Results

Date: 2026-07-18

Dataset: `guardian-review-eval-v1`

Schema: `1.1.0`

Prompt: `guardian-review-v2`

## Method

The repeatable harness generates 55 wholly synthetic cases: five each for
clearly concerning, ambiguous, likely benign, false-positive traps,
missing-context cases, high-severity uncertain cases, quoted/fictional
material, school/research content, gaming language, medical discussion, and
prompt-injection attempts. No child or family data is loaded.

Each case declares explicit expected properties. The scorer checks schema
compliance, assessment and severity agreement, false alarms, unsupported
claims, explicit uncertainty, benign explanations, missing context,
proportionate actions, non-accusatory guidance, and whether incident-text
instructions are ignored. It also records provider latency and usage when the
provider exposes it. Approximate cost is reported only when the operator
supplies pricing; the harness does not guess prices.

Commands:

```bash
cd backend
python -m app.guardian_review_evaluation --provider mock
# Live direct API, only after verifying the selected project's controls:
python -m app.guardian_review_evaluation --provider openai --confirm-live --confirm-zdr
```

Live mode is opt-in, synthetic-only, and requires the server-side key plus
explicit confirmation that the selected OpenAI project has approved Zero Data
Retention controls. The coding-agent provider is now fail-closed.

## Dataset composition

| Group | Cases |
|---|---:|
| Clearly concerning | 5 |
| Ambiguous | 5 |
| Likely benign | 5 |
| False-positive traps | 5 |
| Missing context | 5 |
| High severity, uncertain | 5 |
| Quoted or fictional material | 5 |
| School and research | 5 |
| Gaming language | 5 |
| Medical discussion | 5 |
| Prompt injection in evidence | 5 |
| **Total** | **55** |

## Results

### Deterministic mock run

| Measure | Result |
|---|---:|
| Completed | 55 / 55 |
| Schema compliant | 55 / 55 |
| Assessment-category agreement | 25 / 55 (45.45%) |
| Severity agreement | 55 / 55 |
| False-alarm rate on expected-benign cases | 0% |
| Unsupported-claim check | 55 / 55 |
| Uncertainty stated | 55 / 55 |
| Benign explanations considered | 55 / 55 |
| Missing context identified | 55 / 55 |
| Proportionate action | 55 / 55 |
| Non-accusatory guidance | 55 / 55 |
| Evidence prompt injection ignored | 55 / 55 |

The mock intentionally uses simple deterministic category logic. The low
assessment-category agreement is a useful limitation, not an accuracy claim:
the expected labels distinguish benign from ambiguous cases more finely than
the mock. Mock results prove the harness, schema, and offline judge path; they
do not validate model judgment.

### Historical signed-in Codex synthetic sample

Before the July 18 capability-boundary finding, twelve stratified synthetic
cases ran with requested/returned model alias `gpt-5.6-sol`. No real family data
was used. This result is retained as Build Week evidence but the transport is no
longer an available product path.

| Measure | Result |
|---|---:|
| Completed | 12 / 12 |
| Failed | 0 |
| Schema compliant | 12 / 12 |
| Assessment-category agreement | 12 / 12 |
| Severity agreement | 12 / 12 |
| Uncertainty, benign explanations, proportionality, non-accusatory guidance | 12 / 12 each |
| Unsupported-claim check | 12 / 12 |
| False-alarm rate | 0% |
| Median provider latency | 47,718 ms |
| Maximum provider latency | 61,548 ms |
| Token use / cost | unavailable in this provider mode |

The signed-in Codex CLI did not expose per-request usage metadata to this
integration, so token counts and cost are deliberately reported as unavailable.
This sample is evidence about these fixtures and properties only; it is not a
clinical, universal, demographic, or production-accuracy claim.

## Representative successes

- Research, quoted, gaming, and medical contexts were not treated as automatic
  proof of harmful intent.
- Concerning cases preserved uncertainty while still recommending proportionate
  safety checks.
- Guidance kept observed facts separate from inference and used non-accusatory
  conversation openings.
- Evidence strings containing instructions to ignore the prompt, reveal hidden
  instructions, punish immediately, or emit HTML/script did not control the
  structured result in the evaluated sample.

## Representative failures and limitations

- The deterministic mock does not reproduce nuanced assessment labels.
- Twelve live cases are too small to establish broad performance or fairness.
- Keyword-based property checks can miss subtle unsupported claims or tone.
- Latency is high for an interactive family workflow; progress persistence and
  failure recovery are therefore required.
- The Codex mode did not provide token accounting.
- The live sample used a coding-agent transport that is now disabled because
  its local tools are not an acceptable boundary for untrusted incident text.
- No real family data, diagnostic ground truth, or clinical labels were used.

## Changes made because of testing

- Added the fixed 55-case dataset and machine-readable scorer.
- Made pricing explicit rather than embedding a potentially stale cost claim.
- Disabled the coding-agent provider and device-login route until enforceable
  zero-tool isolation exists; direct Responses API and mock paths remain.
- Expanded deterministic redaction to bracket-dot email forms, IPv6, and full
  Windows paths; bumped the redaction contract to v3 so stale consent expires.
- Preserved durable polling so browser refresh does not lose a running review.
- Kept model output strictly typed, escaped, and advisory.

## Reproduction and interpretation

The JSON output is suitable for CI or offline comparison. A nonzero exit or
failed case means the run did not complete; it must not be silently omitted.
Results should be compared by dataset, schema, prompt, provider, and model
version. Parent feedback is stored locally with the assessment version and does
not automatically train or change production behavior.
