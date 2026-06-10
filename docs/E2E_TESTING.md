# End-to-End Testing

## Synthetic-events harness

`tests/e2e/test_synthetic_events.py` runs an end-to-end test:

1. Spin up backend with a temp data dir
2. Generate synthetic events from `tests/corpus/safety_test_cases.json`:
   - Safe gaming chat
   - Off-platform contact request
   - Secrecy phrase
   - Scam ("free robux")
   - Bullying escalation
   - Self-harm language
   - Phishing link
   - Plus deliberate false-positive borderline cases
3. POST each event to `/api/events`
4. Wait for classification (with mock Ollama if real Ollama isn't running)
5. Assert risk levels match expected, categories match expected
6. Verify alerts are created for severity ≥ medium
7. Verify dashboard API returns expected alert feed
8. Verify redaction occurred before storage
9. Verify encrypted blobs cannot be read without decrypt path

## Mock Ollama

`backend/tests/fixtures/mock_ollama.py` provides a FastAPI app that emulates the Ollama API and returns canned responses for known prompts. Used when CI doesn't have an Ollama daemon.

## Running

```bash
pytest tests/e2e/
```

With real Ollama:
```bash
GUARDIANNODE_E2E_REAL_OLLAMA=1 pytest tests/e2e/
```

## Manual acceptance test (release gate)

Documented in the rollout plan — fresh Windows 11 VM, run the installer, verify all 13 steps pass.
