# If you forget your parent password

You wrote down a 12-word **recovery code** when you set up GuardianNode. It
resets dashboard access only; it does not back up or reconstruct the evidence
encryption key.

## On the dashboard

1. Open the dashboard URL.
2. Click **"Forgot password"** on the sign-in page.
3. Enter your 12 words exactly as written (lowercase, spaces between words). Order matters.
4. Set a new password.
5. Sign in with the new password.

## If you lost BOTH the password AND the recovery code

This is a deliberate dead-end for dashboard access. GuardianNode is local-first
and we have no back door. If you still have a backup of the backend data
directory, including the evidence master key (`keys/master.key`,
`keys/master.key.dpapi` on the original Windows machine, or a portable
master-key backup), encrypted evidence may be recoverable after restoring that
backup.

Options:

- **Start fresh only after a backup.** The installer does not expose a
  `/FORCE_RESET` shortcut. Stop GuardianNode, back up the complete ProgramData
  directory, uninstall, and have a technical administrator move the old data
  directory aside before reinstalling. Do not delete it until you have decided
  historical evidence is no longer needed. A fresh install requires every
  child device to be paired again.

- **Restore from a backup.** If you backed up the backend data directory and
  evidence master key, restore that backup. DPAPI-wrapped Windows keys are
  machine-bound; use a portable key backup when moving to another PC.

## Best practice for the recovery code

- Write it on paper. Don't save it as a screenshot or text file — those can be encrypted by ransomware or read by an attacker on the same PC.
- Store it where you keep important documents (filing cabinet, fireproof box, sealed envelope).
- Consider storing a copy in a different physical location (parent's house, safety deposit box).
- A trusted password manager (1Password, Bitwarden, KeePass) is also acceptable.
- Do NOT store it in the same Windows account/PC as GuardianNode is installed on, where ransomware could encrypt both at once.

Also back up the backend data directory if you need to preserve encrypted
evidence. Without the evidence master key or a portable key backup, encrypted
evidence may not be recoverable.
