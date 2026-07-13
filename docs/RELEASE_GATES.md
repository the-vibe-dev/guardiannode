# Closed Beta Release Gates

GuardianNode is eligible for a closed technical beta only when every required
gate below passes on the same commit. A feature being present in source does not
make its deployment mode supported.

## Maturity vocabulary

| Label | Meaning |
|---|---|
| Code present | An implementation exists in the repository. |
| Automated tested | Repeatable tests exercise the documented behavior. |
| Platform qualified | The exact deployment shape passed its clean-machine gate. |
| Field validated | Credential-scrubbed evidence exists from use outside unit-test fixtures. |
| Production ready | Not currently claimed for any GuardianNode deployment. |

## Required release gates

| Area | Required evidence |
|---|---|
| Native installation | Clean Windows install completes and services/tasks start in the intended accounts. |
| Docker installation | Production images build and a clean Compose stack becomes ready. |
| Pairing | A one-time code or local bootstrap pairs exactly one device and cannot be replayed. |
| Screenshot capture | A visible test frame is captured from the child session with correct monitor/DPI handling. |
| OCR | The configured engine and languages are ready; a unique canary phrase is extracted. |
| Rule classification | The canary phrase triggers the expected deterministic category and severity. |
| Local-model classification | Required Ollama endpoints and configured models are present and judge the canary. |
| Alert creation | Processing produces the expected persisted risk result and parent-visible alert. |
| Parent review | The authenticated dashboard displays the alert and retained evidence according to policy. |
| Upgrade | Supported prior state upgrades with a verified pre-migration backup and preserved identity. |
| Repair | Repair preserves configuration, device identity, database history, and protected state. |
| Uninstall | Runtime processes, services, tasks, rules, and application files are removed; intentionally retained data is reported. |

## Deployment qualification

| Deployment | Current status | Promotion requirement |
|---|---|---|
| Native all-in-one Windows | Closed-beta candidate | Current Windows golden install/reboot/upgrade/uninstall gate. |
| Docker Compose | Closed-beta candidate | Keep the required clean OCR-to-alert CI gate green; qualify optional languages and vision modes separately. |
| Source evaluation on loopback | Technical evaluation | Locked install plus backend, agent, dashboard, and migration suites. |
| Separated private network | Restricted | Plan 2 secure-transport and network qualification. |
| Public internet exposure | Unsupported | No promotion path in this plan. |

## Fail-closed rules

- `/api/health/live` proves only that the process is alive.
- `/api/health/ready` must return HTTP 503 when storage, schema, encryption,
  workers, OCR, language data, or any dependency required by the selected
  classifier mode is unavailable.
- Accepting a screenshot is not a passing canary. The expected OCR text,
  classification, and alert must all be observed.
- A failed migration or qualification run cannot publish release artifacts.

Release evidence belongs under `docs/release-validation/`. Raw evidence and
credentials stay outside the repository.
