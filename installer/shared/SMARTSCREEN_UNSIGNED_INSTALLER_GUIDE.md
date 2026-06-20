# Unsigned Windows Installer Guidance

This mirrors the parent-facing guide at
`docs/PARENT_GUIDES/when-windows-says-protected-your-pc.md`.

GuardianNode alpha Windows installers are not yet code-signed. Windows may show:

> Windows protected your PC

This warning means Windows does not recognize the publisher reputation for this
download. It does not prove the file is safe or unsafe. Only install builds you
created yourself or downloaded from the official repository release page.

Suggested text:

> GuardianNode is an unsigned alpha build. Only continue if you downloaded it
> from github.com/the-vibe-dev/guardiannode/releases or built it yourself. Verify
> SHA-256 hashes when they are available.

Steps:

1. Confirm you downloaded the installer from the official releases page.
2. Compare the file's SHA-256 hash to the published hash when available.
3. In SmartScreen, choose **More info**.
4. Choose **Run anyway**.

If the hash does not match, delete the file and download again from the official
repository release page. Code signing is planned for production releases.
