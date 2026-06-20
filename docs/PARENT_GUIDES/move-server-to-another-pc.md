# Move The Server To Another PC

GuardianNode does not yet ship an automated dashboard migration tool. The
planned migration flow will eventually cover pairing codes, encrypted transfer,
device token rotation, and rollback. For the alpha, treat server migration as a
manual administrator task.

## Manual Alpha Path

Use this only if you are comfortable backing up and restoring local application
data.

1. Stop GuardianNode on the old server or all-in-one PC.
2. Create a portable master-key backup from the backend environment. From a
   source checkout, run this in the `backend/` directory:
   ```bash
   python -m app.services.encryption export-key-backup ./guardiannode-master-key-backup.json
   ```
   Use a strong passphrase and store it separately.
3. Back up the full backend data directory, including:
   - `guardiannode.db`
   - the encrypted evidence/blob directory
   - `keys/master.key` or `keys/master.key.dpapi`
   - configuration files you changed
4. Install GuardianNode on the new server using the normal server install guide.
5. Stop GuardianNode on the new server before first use.
6. Restore the old backend data directory onto the new server, preserving file
   ownership and permissions.
7. Restore the portable key backup if the restored key is machine-bound or
   missing:
   ```bash
   python -m app.services.encryption import-key-backup ./guardiannode-master-key-backup.json
   ```
8. Start GuardianNode on the new server.
9. Open the dashboard and confirm historical alerts, devices, and settings are
   present.
10. Reconfigure each child-device agent to point to the new server URL, then test
   that new events arrive.

Do not delete the old server data until you have verified the new server is
working and you have a separate backup.

## Important Notes

- The recovery code resets dashboard access only. It does not reconstruct the
  evidence master key.
- If the evidence master key and portable backup are lost, encrypted evidence
  may not be recoverable.
- Separated mode uses local-network HTTP unless you place GuardianNode behind
  TLS, Tailscale, WireGuard, or a trusted reverse proxy.
- Device token rotation during migration is planned, not currently automated.

## Planned Automated Migration

Future versions may add a dashboard-assisted migration workflow. Until that
exists in the product, docs should not assume a **Settings -> Migration** page
or migration pairing code.
