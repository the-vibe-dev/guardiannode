# Contributing to GuardianNode

GuardianNode is a child-safety project. Contributions are valued and we want to make it easy to help. Read this short doc first.

## Code of conduct

By participating you agree to abide by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be kind. This project deals with sensitive topics (grooming, self-harm, exploitation) — be considerate in issue threads and PR reviews.

## High-impact contributions

These are the contributions we need most:

1. **New detection rules** in `backend/app/services/risk_rules.py` for grooming/scam/bullying patterns we haven't covered.
2. **Better OCR region configs** for specific games and apps in `agent-windows/ocr_regions/`. Even just verifying our existing configs against the current Roblox/Discord UI helps.
3. **Translations** of the parent-facing UI and parent guides.
4. **Synthetic test corpus** entries in `tests/corpus/safety_test_cases.json`. We never use real child data; synthetic examples drive our classifier evaluation.
5. **Reports of false positives and false negatives** from real deployments. Issue template: `safety_concern`.
6. **Capture/OCR tuning** so on-screen content from specific platforms (TikTok, Snapchat web, etc.) is read reliably from screenshots.

## Development setup

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Dashboard
```bash
cd dashboard
npm install
npm run dev
```

### Agent (Windows only for production; Linux works for development/testing)
```bash
cd agent-windows
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
python -m src.main --dry-run
```

### Run the whole stack with Docker
```bash
cd installer/server-linux
docker compose up
```

### Build installers on Linux (Wine)
```bash
./installer/build/build_all.sh
# Outputs: installer/build/dist/*.exe
```

## Pull request guidelines

- **One concern per PR.** Smaller PRs ship faster and are easier to review.
- **Tests required for new code paths.** We aim for >70% coverage on `backend/app/services/`.
- **No new outbound network calls.** This is a privacy promise — get explicit reviewer approval if you genuinely need one (e.g. SMTP for notifications already exists).
- **No bundled model weights.** Models are pulled via Ollama at install time; never committed to the repo.
- **License compatibility.** Default-allowed: MIT, Apache-2.0, BSD-2/3, ISC. MPL-2.0 with review. AGPL/GPL deps must be optional plugins, not hard dependencies. See [`DEPENDENCY_POLICY.md`](DEPENDENCY_POLICY.md).
- **Update docs.** If you change a rule, update `docs/CLASSIFIER.md`. If you change retention, update `PRIVACY.md`. If you change install flow, update the parent guides.

## Branching

- Default branch: `main`
- Feature branches: `feat/<short-name>`
- Bug fixes: `fix/<short-name>`
- Releases: tagged `v0.x.y`

## Reviewing safety-sensitive code

Reviewers, when looking at PRs that touch `backend/app/services/redaction.py`, `backend/app/services/encryption.py`, `backend/app/services/classifier.py`, or any installer anti-tamper code, please:
1. Read the surrounding test cases.
2. Think about what a determined teen would try to bypass.
3. Think about whether the change could cause a false-negative on a genuine grooming attempt.
4. Comment your reasoning, not just `LGTM`.

## Disclosures and disclaimers

- We will not accept contributions that add cloud telemetry by default.
- We will not accept contributions that add stealth/spyware behavior.
- We will not accept contributions that ship raw system-wide keylogging.
- We will not accept contributions whose primary purpose is monitoring adults who haven't consented to monitoring.

If you're unsure whether your idea fits the project, open a discussion before writing code.

Thank you for helping.
