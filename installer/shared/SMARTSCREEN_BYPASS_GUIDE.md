# Help text for parents when SmartScreen blocks the installer

Lives at `docs/PARENT_GUIDES/when-windows-says-protected-your-pc.md`. Mirrored here for the installer landing page.

Short version embedded in the installer "More info" link:

> **Why this warning?**
>
> GuardianNode is in beta and not yet code-signed. Windows shows this warning for any program from a publisher it doesn't recognize. The warning is not a virus alert.
>
> **Before you click Run anyway:**
> 1. Confirm you downloaded the installer from the official releases page (github.com/the-vibe-dev/guardiannode/releases).
> 2. Compare the file's SHA-256 hash to the published hash on that page.
> 3. Click "More info" then "Run anyway".
>
> If the hash doesn't match, the file may have been tampered with — delete it and re-download.

We will add a code-signing certificate in a future release to remove this warning.
