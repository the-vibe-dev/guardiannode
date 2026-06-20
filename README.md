<div align="center">

<img src="assets/brand/logo-horizontal.png" alt="GuardianNode" width="560">

<br>

[![tests](https://github.com/the-vibe-dev/guardiannode/actions/workflows/test.yml/badge.svg)](https://github.com/the-vibe-dev/guardiannode/actions/workflows/test.yml)
[![docs](https://github.com/the-vibe-dev/guardiannode/actions/workflows/deploy-docs.yml/badge.svg)](https://the-vibe-dev.github.io/guardiannode/)
[![license](https://img.shields.io/badge/license-AGPL--3.0-275E3D)](LICENSE)
[![release](https://img.shields.io/github/v/release/the-vibe-dev/guardiannode?color=0D3B4A)](https://github.com/the-vibe-dev/guardiannode/releases)

# GuardianNode Alpha / Developer Preview

**Local-first AI safety monitoring for families.**

[Documentation](https://the-vibe-dev.github.io/guardiannode/) ·
[Install guides](https://the-vibe-dev.github.io/guardiannode/PARENT_GUIDES/install-on-one-pc/) ·
[Known limitations](KNOWN_LIMITATIONS.md) ·
[Release checklist](RELEASE_CHECKLIST.md) ·
[Support development](docs/SUPPORT.md)

</div>

GuardianNode is an early local-first AI safety monitor for families. It helps
parents review risk signals from a child's Windows device using local
screenshots/OCR/vision/text classification, a local backend, Ollama model
support, encrypted evidence storage, and a parent dashboard.

- Local-first by default
- Parent-owned backend
- Ollama model support
- Screenshot/OCR/vision/text safety pipeline
- Encrypted local evidence storage
- Parent review dashboard
- No cloud account required
- No subscription required
- No raw keylogging
- AGPL-3.0 open source

> **Alpha status**
>
> GuardianNode is alpha software. It may miss risks, create false positives,
> break during setup, or consume significant system resources. Do not rely on it
> as the only child-safety measure. It is not an emergency service and is not a
> substitute for parenting, communication, or professional support.

GuardianNode is for parents and guardians monitoring devices they own or
administer for their own children. It is not stealthware, employee monitoring
software, a keylogger, or a tool for credential theft. The Windows agent is
visible through its tray/status UI and the backend is operated by the parent.

## Deployment Shapes

### All-in-one

Run the Windows agent, backend, dashboard, and Ollama on one family PC. This is
the simplest alpha test path and keeps traffic on loopback by default.

### Separated

Run the Windows child-device agent on the child's PC and run the backend,
dashboard, and Ollama on a parent-owned Windows or Linux server on the same
trusted LAN.

Separated mode currently uses local-network HTTP unless you place GuardianNode
behind TLS, Tailscale, WireGuard, or a trusted reverse proxy. Use single-machine
mode or a trusted LAN/VPN for alpha testing. Built-in TLS/mTLS is planned. See
[Secure LAN setup](docs/SECURE_LAN_SETUP.md).

## What It Monitors

GuardianNode reviews visible screen content from the configured Windows session.
Current installer defaults enable visible desktop screenshot capture so parents
should assume screenshots may contain sensitive on-screen content. Depending on
policy/settings, deployments may use full-screen captures or capture only when
configured apps are active.

GuardianNode can process:

- Visible screen/app activity from configured Windows sessions
- OCR text from screenshots
- Vision model analysis of screenshots/images
- Browser/app activity where collectors support it
- Risk categories such as grooming, off-platform contact attempts, bullying,
  self-harm language, explicit/sexual content, gore/violence, scams/phishing,
  suspicious links, and private-info sharing

Parents should configure capture scope and retention carefully. Evidence is for
parent/admin review and may include private messages, screenshots, names, URLs,
or other sensitive material visible on the child device.

## What It Does Not Do

- Does not perform raw system-wide keylogging
- Does not secretly install itself
- Does not send child data to a GuardianNode cloud
- Cannot detect every risk
- Does not replace platform parental controls
- Does not replace emergency intervention

GuardianNode may apply basic text filtering/redaction in some collectors, but
parents should assume captured evidence can contain sensitive on-screen
information. Evidence is stored locally and encrypted for parent/admin review.

## System Requirements

Windows 10/11 64-bit is the current child-device target. The server side runs on
Windows or Linux. Ollama model performance depends heavily on CPU/GPU/RAM.

| Tier | Hardware | What it catches |
|---|---|---|
| `vision_only` | NVIDIA GPU, 6-12 GB VRAM | Screenshots/images plus OCR/text risk signals in one vision pass |
| `text_only` | No GPU or low VRAM, 8+ GB RAM | OCR/text risks only; visual-only content may be missed |
| `full` | NVIDIA GPU, 16+ GB VRAM or split endpoints | Vision plus separate text model kept available |

Model choices are suggestions. GuardianNode does not bundle model weights; users
must review the license and performance of any Ollama model they install. See
[MODEL_LICENSES.md](MODEL_LICENSES.md).

## Quick Start

### Single PC

1. Download `GuardianNodeChildSetup-0.1.0-alpha.1.exe` from
   [Releases](https://github.com/the-vibe-dev/guardiannode/releases) once
   alpha artifacts are published.
2. Run the installer and choose **Install everything on this PC**.
3. Finish setup in the local dashboard at `http://127.0.0.1:8787`.
4. Create the parent account and write down the recovery code.
5. Back up the backend data directory, especially the local encryption key file.

### Linux Server + Windows Child PC

On the server:

```bash
curl -fsSL https://raw.githubusercontent.com/the-vibe-dev/guardiannode/v0.1.0-alpha.1/installer/server-linux/install.sh | sudo bash
```

Or with Docker:

```bash
git clone https://github.com/the-vibe-dev/guardiannode.git
cd guardiannode/installer/server-linux
docker compose up -d
```

Open `http://127.0.0.1:8787/setup` on the server, enter the one-time setup token
printed by the installer or stored in the server token file, create the parent
account, and pull models. Then follow the manual LAN binding/firewall steps in
the server + child guide before using **Devices -> Add device** to pair the child PC with
`GuardianNodeChildSetup-0.1.0-alpha.1.exe`.

Do not expose the backend directly to the public internet during alpha testing.

## Evidence Encryption And Recovery

Evidence encryption uses a local `master.key` file generated by the backend. The
recovery code resets dashboard access only and does not derive or reconstruct
the evidence encryption key. If the master key is lost, encrypted evidence may
not be recoverable. Back up the backend data directory and protect it like other
sensitive family records.

## Documentation

For parents:

- [Install on one PC](docs/PARENT_GUIDES/install-on-one-pc.md)
- [Install on a server + child PC](docs/PARENT_GUIDES/install-server-and-child.md)
- [Privacy & alert settings](docs/PARENT_GUIDES/privacy-and-alert-settings.md)
- [When Windows says "Protected your PC"](docs/PARENT_GUIDES/when-windows-says-protected-your-pc.md)
- [Known limitations](KNOWN_LIMITATIONS.md)
- [What this cannot stop](docs/PARENT_GUIDES/what-this-cannot-stop.md)

For developers:

- [Architecture](docs/ARCHITECTURE.md)
- [Backend setup](docs/BACKEND_SETUP.md)
- [Windows agent](docs/AGENT_WINDOWS.md)
- [Dashboard](docs/DASHBOARD.md)
- [Secure LAN setup](docs/SECURE_LAN_SETUP.md)
- [Roadmap](docs/ROADMAP.md)
- [Launch messaging](docs/LAUNCH_MESSAGING.md)
- [Release checklist](RELEASE_CHECKLIST.md)

## Support Development

GuardianNode is AGPL-3.0 open-source software with no cloud account or
subscription required. Donations can help fund test hardware, installer signing,
documentation, and platform work. See [Support development](docs/SUPPORT.md).

## Security And Privacy

Read [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) before using
GuardianNode with real family data. Do not upload child screenshots, private
messages, logs containing personal information, or evidence exports to public
GitHub issues.

## License

GuardianNode is licensed under the GNU Affero General Public License v3.0. See
[LICENSE](LICENSE). Commercial licensing may be available separately; see
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

Bundled third-party components are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Ollama model guidance is in
[MODEL_LICENSES.md](MODEL_LICENSES.md).
