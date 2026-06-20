# Launch Messaging

Use this as the source of truth for public alpha posts. Keep the tone honest:
GuardianNode is alpha/developer-preview software for parents and guardians
monitoring devices they own or administer for their own children.

## X Post

GuardianNode is now in alpha/developer preview.

It is a local-first AI safety monitor for families: a visible Windows agent,
parent-owned backend, Ollama OCR/vision/text classification, encrypted local
evidence storage, and a parent dashboard.

No cloud account. No subscription. No raw keylogging. AGPL-3.0.

Alpha means rough edges: setup may break, models may miss risks, false positives
will happen, and it is not an emergency service or a substitute for parenting,
communication, platform parental controls, or professional support.

Repo: https://github.com/the-vibe-dev/guardiannode

## Reply: What It Monitors

GuardianNode reviews visible screen content from configured Windows sessions.
Depending on policy settings, screenshots may include the visible desktop or
only configured apps.

Parents should assume captured evidence may contain sensitive on-screen
information and should configure retention and access carefully.

## Reply: Privacy Model

By default, GuardianNode stores evidence locally on hardware the parent controls.
There is no GuardianNode vendor cloud by default. Model weights are
user-installed, and external notifications are optional and parent-configured.

Separated LAN mode should be used only on a trusted LAN/VPN or behind TLS.

## Reply: What It Is Not

GuardianNode is not stealthware, spyware, employee monitoring software, a raw
keylogger, credential theft tooling, or a public-internet SaaS backend.

It has a visible child-device status/tray UI and is intended for transparent
family safety deployments.

## Reply: Roadmap

Current child-device focus: Windows.

Platform roadmap after Windows alpha hardening:

1. macOS
2. Android
3. iOS

Mobile platforms need platform-specific design because their permissions,
background processing, stores, and privacy models are different.

## Reply: Support

GuardianNode is AGPL-3.0 open source and does not require a subscription.
Optional donations help fund test hardware, code signing, docs, and platform
work.

Donation details are in the repo docs. Do not post child screenshots, private
messages, evidence exports, or personal logs in public issues.
