# If you forget your parent password

You wrote down a 12-word **recovery code** when you set up GuardianNode. Use it now.

## On the dashboard

1. Open the dashboard URL.
2. Click **"Forgot password"** on the sign-in page.
3. Enter your 12 words exactly as written (lowercase, spaces between words). Order matters.
4. Set a new password.
5. Sign in with the new password.

## During an uninstall

The uninstaller also accepts the recovery code if you've forgotten the password:

1. Run the uninstaller from Programs & Features.
2. When prompted for the password, click **"Use recovery code instead"**.
3. Enter the 12 words.

## If you lost BOTH the password AND the recovery code

This is a deliberate dead-end. GuardianNode is local-first and we have no back door. Without either, your encrypted evidence is permanently lost.

Options:

- **Reinstall fresh.** This wipes the GuardianNode database and starts over. All historical alerts are lost. The agent and dashboard continue to work going forward. To do this, run the installer again with the `/FORCE_RESET` switch:
  ```cmd
  GuardianNodeChildSetup.exe /FORCE_RESET
  ```
  ⚠️ This is irreversible. Only do this if you've truly lost both keys.

- **Restore from a backup.** If you previously exported a backup of the database + recovery code, you can re-import it via the dashboard's **Settings → Backup & Restore** page.

## Best practice for the recovery code

- Write it on paper. Don't save it as a screenshot or text file — those can be encrypted by ransomware or read by an attacker on the same PC.
- Store it where you keep important documents (filing cabinet, fireproof box, sealed envelope).
- Consider storing a copy in a different physical location (parent's house, safety deposit box).
- A trusted password manager (1Password, Bitwarden, KeePass) is also acceptable.
- Do NOT store it in the same Windows account/PC as GuardianNode is installed on, where ransomware could encrypt both at once.
