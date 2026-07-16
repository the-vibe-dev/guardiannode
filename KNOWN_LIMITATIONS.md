# Known Limitations

GuardianNode is alpha/developer-preview software.

- It may miss risky content.
- It may produce false positives.
- Setup, installer behavior, and hardening are still evolving.
- OCR accuracy varies by app, font, theme, resolution, language, and screen
  scaling.
- Vision models may misclassify images or miss important context.
- Local models vary by license, hardware requirements, speed, and quality.
- Screenshot capture may include sensitive on-screen information.
- Guardian Review is a fallible external-model second opinion, not a finding of
  intent, wrongdoing, diagnosis, or legal status.
- Guardian Review redaction is deterministic defense-in-depth, not a guarantee.
  Novel obfuscation, unsupported international identifiers/addresses,
  image-only private information, and relevant destination hostnames may still
  reveal context; the parent must inspect the exact outbound preview.
- ChatGPT/Codex processing follows the connected plan or workspace controls.
  Direct Responses API mode uses `store=false` but is disabled unless the
  operator separately confirms approved Zero Data Retention controls.
- LAN mode may require additional TLS, VPN, or reverse-proxy protection.
- Windows is the current child-device focus. The planned platform order is
  macOS next, then Android, then iOS; those platforms are not current features.
- It is not an emergency service.
- It is not a replacement for platform parental controls.
- It is not a replacement for parent-child conversations, professional support,
  or direct intervention when a child may be in immediate danger.

Use GuardianNode as one tool in a broader child-safety plan.
