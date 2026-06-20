# When Windows says "Protected your PC"

When you try to run `GuardianNodeChildSetup-0.1.0-alpha.1.exe` or `GuardianNodeServerSetup-0.1.0-alpha.1.exe`, Windows may show a blue popup that says:

> **Windows protected your PC**
> Microsoft Defender SmartScreen prevented an unrecognized app from starting. Running this app might put your PC at risk.

This is expected for unsigned alpha builds. It does not prove the file is safe
or unsafe. Only install builds you created yourself or downloaded from the
official repository release page.

## Why this happens

Windows shows this warning for programs whose publisher is not recognized or
whose signing reputation is not established. GuardianNode alpha installers are
not yet code-signed. Code signing is planned for production releases.

## Verify before clicking through

Before clicking through, you should make sure you downloaded the real GuardianNode installer and not something else.

1. **Check the file size** matches what's listed on the [Releases page](https://github.com/the-vibe-dev/guardiannode/releases).
2. **Check the SHA-256 hash**. Open PowerShell (Win + R, type `powershell`, press Enter) and run:
   ```powershell
   Get-FileHash -Algorithm SHA256 "$env:USERPROFILE\Downloads\GuardianNodeChildSetup-0.1.0-alpha.1.exe"
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

## When this changes

Code signing is planned before production releases. Signed builds may still show
reputation warnings until enough users install them.

## Reporting a fake

If you find a download of "GuardianNode" hosted somewhere other than our official GitHub releases, please report it through the private vulnerability flow linked in [SECURITY.md](https://github.com/the-vibe-dev/guardiannode/blob/main/SECURITY.md).
