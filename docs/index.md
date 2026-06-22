---
hide:
  - navigation
  - toc
---

# GuardianNode { .gn-hidden-title }

<div class="gn-hero" markdown>

<img class="gn-hero-logo" src="assets/brand/logo-vertical.png" alt="GuardianNode">

<p class="gn-tagline">
An alpha/developer-preview safety monitor for families that runs on hardware you
own. Local AI helps parents review risk signals from a child's Windows device:
screenshots, OCR, vision/text classification, encrypted local evidence, and a
parent dashboard.
</p>

[Install on one PC](PARENT_GUIDES/install-on-one-pc.md){ .md-button .md-button--primary }
[Server + child PC](PARENT_GUIDES/install-server-and-child.md){ .md-button }
[Known limitations](https://github.com/the-vibe-dev/guardiannode/blob/main/KNOWN_LIMITATIONS.md){ .md-button }
[Support development](SUPPORT.md){ .md-button }

</div>

<div class="gn-cards" markdown>
<div class="gn-card" markdown>
<h3>🔒 Private by Design</h3>
<p>By default, your child's data stays on hardware you control. Classification runs on local AI (Ollama); external notifications are optional and parent-configured, and retained evidence is encrypted for parent review.</p>
</div>
<div class="gn-card" markdown>
<h3>👨‍👩‍👧 Family First</h3>
<p>Built for parents, not IT departments. Pairing uses a 6-digit code and an explicit server URL, and alerts explain what happened and what to do next.</p>
</div>
<div class="gn-card" markdown>
<h3>🤝 Trustworthy</h3>
<p>No stealth mode, ever. A visible tray icon shows the child when monitoring is on. No raw keystroke capture, no password-field collection, and parent-controlled capture scope.</p>
</div>
<div class="gn-card" markdown>
<h3>🧠 Technical & Modern</h3>
<p>Vision LLM reads the screen the way a person would — text and imagery — backed by a deterministic rules engine that works even when the model is down.</p>
</div>
<div class="gn-card" markdown>
<h3>💚 Calm & Supportive</h3>
<p>Severity-ranked alerts with per-category playbooks. It will miss things and sometimes false-alarm — we say so plainly. It's one tool, not a replacement for parenting.</p>
</div>
</div>

## How it works

<div class="gn-flow">
<b>Child PC agent</b> → <b>visible screen screenshots</b> → <b>your own server</b> → <b>local AI + rules</b> → <b>encrypted evidence</b> → <b>parent dashboard alert</b>
</div>

The agent on the child's PC reviews visible screen content from the configured
Windows session. Current installer defaults enable visible desktop screenshot
capture; policy/config can narrow capture to configured apps. Frames go to
**your** backend — the same PC or another machine in your house — where local
models and rules classify risk signals. Retained evidence is stored locally and
encrypted for parent review.

Read the full [architecture](ARCHITECTURE.md), [safety boundaries](SAFETY_BOUNDARIES.md), and [threat model](THREAT_MODEL.md).

## What do I need to run it?

The installer checks your hardware and picks the strongest tier it can run:

| Tier | Hardware | What it catches |
|---|---|---|
| **Full** | NVIDIA GPU with 16+ GB VRAM | Everything, with the most nuance on ambiguous chat |
| **Vision** *(default)* | NVIDIA GPU with 12–15 GB VRAM | Explicit imagery + grooming/self-harm/scam text + your custom watch phrases |
| **Text-only** | Any PC with 8 GB RAM, no GPU | Text risks only — visual-only content (nudity/gore without text) is **not** detected |

No GPU in the kid's PC? Use the [two-machine setup](PARENT_GUIDES/install-server-and-child.md): the child's PC runs only the lightweight agent and a Linux or Windows box with a GPU does the AI work.

## Quick Start From Source

**Alpha scope:** GuardianNode 0.1.0-alpha.1 is a source-code developer preview.
Loopback all-in-one testing is the safest supported shape. Public Windows
installer recommendation and ordinary family deployment are blocked until the
Windows release validation gates pass.

| Mode | Alpha support |
|---|---|
| Source backend on loopback | Supported for technical evaluation |
| Source all-in-one Windows evaluation | Experimental |
| Separated LAN deployment | Advanced/experimental; TLS or VPN required |
| Public Windows installer | Not supported |
| Public Internet exposure | Unsupported |

Start the backend on loopback:

```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e "backend[dev]"
mkdir -p local_config/dev-data
GUARDIANNODE_BIND_HOST=127.0.0.1 \
GUARDIANNODE_BIND_PORT=8787 \
GUARDIANNODE_DATA_DIR=local_config/dev-data \
GUARDIANNODE_ALLOWED_HOSTS=127.0.0.1,localhost,testserver \
GUARDIANNODE_MDNS_ENABLED=false \
GUARDIANNODE_CLASSIFIER_TIER=text_only \
GUARDIANNODE_TEXT_MODEL= \
GUARDIANNODE_VISION_MODEL= \
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8787
```

Build and test the dashboard separately when changing UI code:

```bash
cd dashboard
npm ci
npm run typecheck
npm test -- --run
npm run build
```

Open `http://127.0.0.1:8787/setup`, create the parent account, and write down
the recovery code. Installer paths are maintainer qualification paths only in
this alpha; do not pipe an unverified network response directly into a
privileged shell.

Step-by-step with screenshots: [one PC](PARENT_GUIDES/install-on-one-pc.md) · [server + child PC](PARENT_GUIDES/install-server-and-child.md) · [troubleshooting](PARENT_GUIDES/troubleshooting.md)

## Guides

<div class="gn-cards" markdown>
<div class="gn-card" markdown>
<h3>Getting started</h3>
<p><a href="PARENT_GUIDES/install-on-one-pc/">Install on one PC</a> · <a href="PARENT_GUIDES/install-server-and-child/">Server + child PC</a> · <a href="PARENT_GUIDES/when-windows-says-protected-your-pc/">The Windows SmartScreen warning</a></p>
</div>
<div class="gn-card" markdown>
<h3>Everyday use</h3>
<p><a href="PARENT_GUIDES/pause-monitoring-when-you-use-the-pc/">Pause monitoring when you use the PC</a> · <a href="PARENT_GUIDES/if-you-forget-your-password/">If you forget your password</a> · <a href="PARENT_GUIDES/move-server-to-another-pc/">Move the server</a></p>
</div>
<div class="gn-card" markdown>
<h3>Honest limits</h3>
<p><a href="PARENT_GUIDES/what-this-cannot-stop/">What this cannot stop</a> — phones, school devices, in-person contact. Read this one first.</p>
</div>
<div class="gn-card" markdown>
<h3>For developers</h3>
<p><a href="BACKEND_SETUP/">Backend setup</a> · <a href="AGENT_WINDOWS/">Windows agent</a> · <a href="DASHBOARD/">Dashboard</a> · <a href="https://github.com/the-vibe-dev/guardiannode/blob/main/CONTRIBUTING.md">Contributing</a></p>
</div>
<div class="gn-card" markdown>
<h3>Project support</h3>
<p><a href="ROADMAP/">Roadmap</a> · <a href="SUPPORT/">Donations</a>. GuardianNode stays local-first, open-source, and subscription-free.</p>
</div>
</div>

!!! warning "GuardianNode is assistive software"
    It is not a replacement for parenting, professional support, or emergency services.
    It will miss things. It will sometimes false-alarm. Use it as one of several tools —
    and read [what it cannot stop](PARENT_GUIDES/what-this-cannot-stop.md).

<div class="gn-hero" markdown>
<small>
[Privacy](https://github.com/the-vibe-dev/guardiannode/blob/main/PRIVACY.md) ·
[Security policy](https://github.com/the-vibe-dev/guardiannode/blob/main/SECURITY.md) ·
[Code of conduct](https://github.com/the-vibe-dev/guardiannode/blob/main/CODE_OF_CONDUCT.md) ·
[Support development](SUPPORT.md) ·
AGPL-3.0 licensed
</small>
</div>
