# Windows Build Week qualification — 2026-07-21

## Candidate

- Version: `0.1.0-alpha.3`
- Merge commit: `8c059a05d1c7d0d472dd074b762678cc35fb705f`
- Tag: `guardian-node-build-week-2026-qualified`
- Release workflow: passed
- Installers: checksum verified; unsigned alpha artifacts

## Windows 11 all-in-one node

The exact server installer completed successfully. Backend, broker, and watchdog
services and agent, tray, and Ollama tasks were created. Database schema
`0005_guardian_review_feedback`, OCR readiness, installed model readiness, and
protected filesystem/service ACL checks passed. A rendered Chrome flow passed:
synthetic incident, local reasoning, optional-field removal, exact outbound
preview, cancel-without-send, explicit consent, structured result, refresh/history
recovery, and local feedback.

After reboot the delayed-auto-start services recovered. The local Ollama logon
task did not start reliably on this lab node; rules-only detection remained
usable, and a manual background Ollama start restored model readiness. Treat
unattended Ollama reboot recovery as a disclosed beta limitation.

## Windows 11 child/server path

The exact child installer paired with an isolated staging backend using a
one-use code. The child installed no local backend or Ollama task. Broker and
watchdog services plus agent and tray tasks ran, device heartbeat remained
current, and real agent events reached the server.

A labelled synthetic gaming fixture was displayed on the child. The actual
agent captured it, uploaded encrypted evidence, and the server ran Tesseract OCR
plus deterministic rules. The resulting persisted alert was medium severity,
category `bullying`, rule `bullying_keywords`. No real child or family data was
used.

## Live Guardian Review proof

The parent dashboard loaded the authorized alert, displayed the encrypted
capture, created the exact minimized outbound preview, required explicit
external-processing consent, and submitted through the server-side OpenAI
Responses API. The request asked for `gpt-5.6`; the API returned
`gpt-5.6-sol`. The strict schema `1.1.0` result completed in 36,481 ms and was
persisted with prompt `guardian-review-v2`, redaction
`guardian-review-redaction-v3`, limitations, communication guidance, usage, and
local parent feedback. The temporary key was removed immediately after capture
and staging was restored to mock mode.

`store:false` was used, but GuardianNode cannot independently verify account
retention controls; this proof is not a zero-retention claim.

## Video artifact

- File: `GuardianNode-Guardian-Review-Build-Week-2026.mp4`
- Duration: 168.000 seconds
- Streams: H.264 1280x720, AAC, embedded English captions
- Narration: disclosed AI-generated OpenAI `gpt-4o-mini-tts` Coral voice
- SHA-256: `649e01da5944f193a8801d09dfed3001d0526ddd14fc8d53c8db49ca420b55de`

## Remaining manual gates

- Listen through the final uploaded YouTube transcode and verify it while signed out.
- Complete clean uninstall/reinstall residue testing and Windows 10 qualification.
- Sign release installers before any non-alpha distribution.
- Run `/feedback`, store the Session ID privately, submit Devpost, and preserve confirmation.
