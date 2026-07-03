# End-to-End Testing

## Synthetic-events harness

`tests/e2e/test_synthetic_events.py` runs a CI-safe end-to-end test:

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
3. Complete first-run setup with the one-time setup token
4. Pair a synthetic child device and assign it to a child profile
5. POST each event to `/api/events`
6. Classify with a canned local classifier fixture (no Ollama required)
7. Assert risk levels and categories match expected
8. Verify alerts are created according to policy
9. Verify dashboard APIs return the expected event/alert feeds
10. Review an alert, export encrypted storage, and run retention cleanup

## Classifier mode

The default E2E path does not call Ollama. It monkeypatches the backend text
classifier with responses from `tests/corpus/safety_test_cases.json`, which keeps
CI deterministic and fast. Live Ollama/GPU behavior is validated as a manual
release acceptance pass on a GPU node.

## Running

```bash
cd backend
pytest ../tests/e2e/
```

With real Ollama:
```bash
GUARDIANNODE_E2E_REAL_OLLAMA=1 pytest ../tests/e2e/
```

## Manual acceptance test (release gate)

Documented in the rollout plan — fresh Windows 11 VM, run the installer, verify all 13 steps pass.
