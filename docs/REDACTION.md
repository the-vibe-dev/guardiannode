# Text Filtering And Redaction

GuardianNode includes basic text filtering/redaction helpers for some sensitive
patterns such as card-like numbers, SSNs, password markers, API-key-like tokens,
2FA-code-like snippets, and private-key blocks.

This is best-effort hygiene, not a privacy certainty.

Parents and administrators should assume captured evidence can contain sensitive
on-screen information. Screenshots and extracted text blobs are stored locally
and encrypted for parent/admin review, but operational metadata such as app
names, URLs, timestamps, risk summaries, categories, and audit details may
remain plaintext in SQLite or pending metadata files.

## Where It May Run

- Backend OCR/event ingestion paths may call `backend/app/services/redaction.py`.
- Some older code and schemas use the field name `redacted_text` for extracted
  event text. That name does not mean every sensitive value was removed.

## Limits

- It does not make secret removal certain for classification.
- It does not make secret removal certain for storage.
- It does not sanitize screenshots.
- It does not replace careful capture-scope and retention settings.

## Maintenance

Add or adjust patterns in `backend/app/services/redaction.py` and cover them with
synthetic tests in `backend/tests/test_redaction.py`. Do not use real child data
or real secrets in tests or issue reports.
