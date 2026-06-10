# When Windows says "Protected your PC"

When you try to run `GuardianNodeChildSetup.exe` or `GuardianNodeServerSetup.exe`, Windows may show a blue popup that says:

> **Windows protected your PC**
> Microsoft Defender SmartScreen prevented an unrecognized app from starting. Running this app might put your PC at risk.

This is **expected** for the beta release and **does not mean the software is unsafe**. Here's what's actually happening, and how to safely proceed.

## Why this happens

Windows shows this warning for any program whose publisher isn't recognized — usually because the publisher hasn't bought a "code-signing certificate" from Microsoft's chosen vendors (this costs $300–$600/year). GuardianNode is a free, open-source, beta project. We are working on getting a sponsored code-signing certificate. Until then, you'll see this warning.

## Verify before clicking through

Before clicking through, you should make sure you downloaded the real GuardianNode installer and not something else.

1. **Check the file size** matches what's listed on the [Releases page](https://github.com/the-vibe-dev/guardiannode/releases).
2. **Check the SHA-256 hash**. Open PowerShell (Win + R, type `powershell`, press Enter) and run:
   ```powershell
   Get-FileHash -Algorithm SHA256 "$env:USERPROFILE\Downloads\GuardianNodeChildSetup.exe"
   ```
   Compare the output to the hash on the Releases page. They should match exactly.

If the hashes don't match, **do not run the installer**. Delete it and download again from the official Releases page.

## How to click through

Once you've verified the download:

1. In the blue popup, click the small text link **"More info"**.
2. A new button appears: **"Run anyway"**.
3. Click **"Run anyway"**.
4. User Account Control will prompt — click **Yes**.
5. The installer launches.

## What this is not

- It's **not** a virus warning. Real virus warnings say "Threat detected" in red, not "Protected your PC" in blue.
- It's **not** a known-malicious-software warning. If Windows actually thought the file was malicious, it would delete it, not let you click through.
- It's **not** a permanent block. Once you've run the installer once, Windows remembers and won't warn again on that PC.

## When we'll fix this

Our roadmap:
- **v0.2**: Apply for [SignPath.io](https://signpath.io/) free code-signing for OSS projects.
- **v1.0**: Acquire an EV code-signing certificate (sponsored, or community-funded).

After either of those, the SmartScreen warning goes away.

## Reporting a fake

If you find a download of "GuardianNode" hosted somewhere other than our official GitHub releases, please report it to us — that's likely a malicious impersonation. Email: `security@guardiannode.example`.
