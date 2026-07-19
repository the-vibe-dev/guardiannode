# GuardianNode Build Week Video Script and Shot List

Target runtime: 2:48. Use voiceover. Record only functional UI with the
synthetic demo. Before recording, hide secrets, private email, internal IPs,
hostnames, browser bookmarks, notifications, and unrelated windows. Use mock
mode unless the direct API project and recording environment are explicitly
approved.

Production assets are under [`video/`](video/VIDEO_PRODUCTION_RUNBOOK.md): a
2:48 voiceover, SRT captions, machine-readable shot manifest, and the exact
Codex computer prompt. The repository helper
`scripts/start_build_week_video_demo.py` launches a disposable mock-only server
without reading an existing family database or loading an API key.

## 0:00–0:20 — The problem

**Shot:** Title card, then a close crop of the synthetic incident list.

**Voiceover:** “A worrying message can be serious, a joke, or school research.
Parents need enough context to protect a child without turning an uncertain
signal into an accusation. GuardianNode keeps detection local, then helps a
parent decide what to ask next.”

## 0:20–0:40 — Existing GuardianNode platform

**Shot:** Devices health, local Models status, then Risk Feed. Add an on-screen
label: “Existing before Build Week.”

**Voiceover:** “Before Build Week, GuardianNode already had a visible Windows
agent, a parent-owned backend, local rules and optional Ollama models, encrypted
evidence, the dashboard, authentication, and installers. Portions of the prior
web UI were Claude-assisted; the platform was built with Codex assistance.”

## 0:40–1:05 — Local synthetic detection

**Shot:** Open **Synthetic demo**, show “synthetic only,” choose “Unknown contact
requesting secrecy,” trigger it, and open the incident. Show local severity,
categories, and detector reasoning.

**Voiceover:** “For judges, six resettable scenarios use no real child data.
This one asks a synthetic child to keep a secret and move platforms. The normal
local detector creates and persists the incident first. Guardian Review never
replaces that local path.”

## 1:05–1:45 — Guardian Review workflow

**Shot:** Open Guardian Review. Select coarse relationship/repetition/goal
context. Show locally stored evidence separately, remove optional parent
context, create preview, slowly scroll the exact minimized JSON, then check the
consent box and submit. Show queued/loading and completed states.

**Voiceover:** “Guardian Review loads the authorized incident on the server. A
deterministic minimizer removes names, accounts, contact details, paths, device
identifiers, precise locations, and unrelated context. The parent sees the
exact outbound JSON and can remove optional fields. Nothing external happens
until this explicit action. Live mode uses the server-side OpenAI Responses API
with configurable GPT-5.6, no tools, `store: false`, and a strict schema. This
demo uses deterministic mock mode, so it needs no key or network.”

## 1:45–2:10 — Communication guidance

**Shot:** Scroll the completed result: observed facts versus inference,
uncertainty, benign explanations, unknowns, tone, opening words, questions,
phrases to avoid, actions, escalation indicators. Mark “Helpful” and “Missing
context.”

**Voiceover:** “The result is not presented as fact. It separates observation
from inference, surfaces benign explanations and missing context, and suggests
calm opening words. Safety actions are separate from later discipline. Feedback
stays local and one response never silently retrains production behavior.”

## 2:10–2:35 — Codex and GPT-5.6 development story

**Shot:** Repository baseline tag and Build Week commit list, strict schema,
evaluation results table, then passing test summary. Avoid terminal history that
could contain secrets.

**Voiceover:** “Codex helped preserve the baseline, trace the real code path,
implement and test the extension, build 55 synthetic evaluation cases, and run
adversarial review. That review changed the product: we disabled a convenient
ChatGPT coding-agent transport because local tools were the wrong privacy
boundary. Runtime review stays on the tool-free Responses API.”

## 2:35–2:48 — Privacy and close

**Shot:** Return to exact preview/cancel, then logo and repository link. On-screen
text: “AI guidance. Parent decision.”

**Voiceover:** “GuardianNode keeps the parent in control of what leaves the
device and what happens next. It is an alpha second opinion—not a diagnosis,
emergency service, punishment engine, or replacement for a trusted family
conversation.”

## Recording verification

- [ ] Runtime is between 2:35 and 2:50.
- [ ] Voiceover is clear; the story does not rely on music or silent captions.
- [ ] Every shown control works in the recorded build.
- [ ] “Existing” and “Build Week extension” labels match repository evidence.
- [ ] No key, token, private email, internal address, real child data, or real
      family account appears in video/audio/metadata.
- [ ] Claims match `EVALUATION_RESULTS.md` and do not imply clinical accuracy.
- [ ] YouTube visibility is Public and the video works while logged out.
- [ ] Repository links work while logged out, or judge access is confirmed.
