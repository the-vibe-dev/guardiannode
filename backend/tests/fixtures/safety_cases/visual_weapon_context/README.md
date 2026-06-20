Visual-only cases (a weapon visible on screen with no risky text) require the
vision tier and a live vision model, so they cannot run as deterministic CI
fixtures. See `vision_expectations.json` for the documented expected behavior;
model-integration tests covering it are optional/slow and not part of normal CI.
