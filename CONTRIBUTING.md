# Contributing to GuardianNode

Thanks for helping GuardianNode. This project exists to give families a
local-first, transparent child-safety tool without requiring a cloud account or
subscription.

## Project Values

- Local-first by default
- Parent-owned backend and evidence store
- Visible, transparent monitoring
- No raw keylogging
- No stealth/persistence/evasion behavior
- No cloud telemetry by default
- Synthetic fixtures and tests, never real child data
- Model/plugin licenses documented before use

GuardianNode is for parents/guardians monitoring child devices they own or
administer. Contributions that reframe it as employee surveillance, spyware, or
credential capture are out of scope.

## License

Unless otherwise noted, contributions are accepted under the GNU Affero General
Public License v3.0. By opening a pull request, you agree that your contribution
may be distributed under AGPL-3.0 with the rest of the project.

## Development Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### Dashboard

```bash
cd dashboard
npm ci
npm run typecheck
npm test -- --run
npm run build
```

### Agent

```bash
cd agent-windows
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m src.main --dry-run
```

### Docker Server

```bash
cd installer/server-linux
docker compose config
docker compose up -d
```

## Contribution Rules

- Do not add raw system-wide keylogging.
- Do not add hidden install, stealth UI, evasion, or malware-like persistence.
- Do not add cloud telemetry, analytics, crash reporting, or third-party model
  APIs by default.
- Do not commit model weights.
- Do not use real child screenshots, private messages, or evidence logs in
  tests, fixtures, screenshots, issues, or PRs.
- Use synthetic fixtures only.
- Keep model/plugin/dependency licenses documented in `MODEL_LICENSES.md` and
  `THIRD_PARTY_NOTICES.md`.
- Update parent-facing docs when changing setup, capture scope, evidence
  handling, security, privacy, retention, or release behavior.

## High-Impact Work

- Detection rules for grooming, scams, bullying, self-harm, and private-info
  sharing
- OCR/capture tuning for common apps and games
- Synthetic test cases for false positives and false negatives
- Installer reliability and downgrade/upgrade testing
- Clear parent-facing documentation
- LAN/TLS hardening and future mTLS/device certificate work

## Security And Sensitive Reports

Do not post child evidence or exploitable security details in public issues. See
[SECURITY.md](SECURITY.md) for private reporting guidance.
