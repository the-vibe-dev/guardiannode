# Synthetic Build Week Screenshots

These images were captured from the real `0.1.0-alpha.2` dashboard bundle with
`scripts/capture_build_week_screenshots.py`. The helper starts a disposable
backend, creates a synthetic parent account, selects the deterministic mock
provider, and exercises the actual API/UI path. It never opens an existing
GuardianNode data directory and makes no external model request.

1. [Synthetic scenario picker](01-synthetic-scenario-picker.png)
2. [Local detection created](02-local-detection-created.png)
3. [Synthetic incident and local reasoning](03-synthetic-incident.png)
4. [Exact outbound preview](04-exact-outbound-preview.png)
5. [Communication plan and parent feedback](05-communication-plan-and-feedback.png)

The images contain only manufactured scenario text and the label “Synthetic
Demo Parent.” Before publication, the owner should still inspect the final files
and video frame for metadata or accidental desktop overlays.
