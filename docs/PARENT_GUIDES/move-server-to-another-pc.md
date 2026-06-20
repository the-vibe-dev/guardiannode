# Move The Server To Another PC

GuardianNode does not yet ship an automated dashboard migration tool. The
planned migration flow will eventually cover pairing codes, encrypted transfer,
device token rotation, and rollback. For the alpha, treat server migration as a
manual administrator task.

## Manual Alpha Path

Use this only if you are comfortable backing up and restoring local application
data.

1. Stop GuardianNode on the old server or all-in-one PC.
2. Back up the full backend data directory, including:
   - `guardiannode.db`
   - the encrypted evidence/blob directory
   - `keys/master.key`
   - configuration files you changed
3. Install GuardianNode on the new server using the normal server install guide.
4. Stop GuardianNode on the new server before first use.
5. Restore the old backend data directory onto the new server, preserving file
   ownership and permissions.
6. Start GuardianNode on the new server.
7. Open the dashboard and confirm historical alerts, devices, and settings are
   present.
8. Reconfigure each child-device agent to point to the new server URL, then test
   that new events arrive.

Do not delete the old server data until you have verified the new server is
working and you have a separate backup.

## Important Notes

- The recovery code resets dashboard access only. It does not reconstruct
  `keys/master.key`.
- If `keys/master.key` is lost, encrypted evidence may not be recoverable.
- Separated mode uses local-network HTTP unless you place GuardianNode behind
  TLS, Tailscale, WireGuard, or a trusted reverse proxy.
- Device token rotation during migration is planned, not currently automated.

## Planned Automated Migration

Future versions may add a dashboard-assisted migration workflow. Until that
exists in the product, docs should not assume a **Settings -> Migration** page
or migration pairing code.
