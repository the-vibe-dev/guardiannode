# Redaction

Before any captured content is classified or stored, GuardianNode redacts likely secrets. This protects the child's accounts and the family's finances even from the eyes of the parent reviewing alerts.

## What we redact

| Pattern | Replaced with | Notes |
|---|---|---|
| Credit card numbers (16-digit, Luhn-valid) | `[REDACTED:card]` | Major card brands |
| US SSN (`XXX-XX-XXXX`) | `[REDACTED:ssn]` | |
| Email-style 2FA / verification codes (6-8 digits in "code: NNNN" context) | `[REDACTED:2fa]` | Context-aware |
| Bearer tokens / API keys (`sk-...`, `ghp_...`, `xoxb-...`) | `[REDACTED:apikey]` | Common prefixes |
| Private keys / PEM blocks | `[REDACTED:privkey]` | Whole block |
| Crypto recovery phrases (12/24 BIP39 words in sequence) | `[REDACTED:seed]` | |
| Passwords after `password:` / `pwd:` markers | `[REDACTED:pwd]` | Context-aware |

## Where redaction runs

1. **In the agent** — before transmission over loopback/LAN.
2. **In the backend** — defense in depth, including on text recovered by OCR from screenshots.

## What we deliberately do NOT redact

- Names of people (often important for grooming detection)
- Locations mentioned in chat (often important for risk assessment)
- Phone numbers shared in chat (red flag for off-platform contact)
- Email addresses shared in chat (same)

## False positives

A 16-digit number that passes the Luhn check but isn't a card will be redacted. Acceptable trade-off — leaking a real card is worse than opaque redaction.

## How to extend

Add a regex to `backend/app/services/redaction.py` → `_PATTERNS`. Add tests in `backend/tests/test_redaction.py` that confirm both matches and non-matches.

## Logging

Redaction output is logged in summary form ("redacted 1 card, 2 2fa codes") — never the redacted content itself. Raw input is never logged.
