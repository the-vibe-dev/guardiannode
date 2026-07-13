# GuardianNode Archive Format

GuardianNode Archive Format version 1 (`.gna`) is the supported recovery
container. It replaces the legacy `.gnexport` format, which cannot restore all
encrypted database fields and must not be described as a complete backup.

## Security model

A `.gna` file has a small canonical JSON header followed by a chunked
AES-256-GCM payload. The header is authenticated with every chunk. The random
archive key is wrapped either with:

- an Argon2id-derived key from a passphrase;
- an X25519 offline recovery recipient; or
- the instance master key for a same-instance snapshot.

Portable archives contain the source master key only inside the authenticated
encrypted payload. Passphrases and recovery private keys are never written to the server.
An incorrect credential or changed byte prevents payload release.

The encrypted payload contains an exact SQLite snapshot, encrypted evidence,
typed JSONL records, configuration, version metadata, and a canonical file
manifest. Every file is SHA-256 hashed and the manifest is signed by the
instance Ed25519 identity. Encrypted database values are represented with their
algorithm, record and field binding, nonce, ciphertext, tag, and Base64 value.

## Offline commands

```text
guardiannode-archive keygen recovery-private.pem recovery-public.pem
guardiannode-archive create family-backup.gna --recipient recovery-public.pem
guardiannode-archive inspect family-backup.gna
guardiannode-archive verify family-backup.gna --identity recovery-private.pem
guardiannode-archive extract family-backup.gna ./review --identity recovery-private.pem
guardiannode-archive restore family-backup.gna --target /srv/guardiannode \
  --identity recovery-private.pem --dry-run
```

`inspect` reads only public header metadata. `verify`, `extract`, and `restore`
authenticate the entire archive before publishing files. Restore accepts only
a portable archive and an empty destination; archive merging is intentionally
unsupported.

Store recovery private keys separately from both the server and its backups.
Anyone holding a portable archive and its passphrase or recovery private key
can recover the family's data.

## Scheduled complete backups

Generate a recovery key with `guardiannode-archive keygen`, store the private
key offline, and paste only the public PEM into **Settings → Complete recovery
backups**. Scheduled backups are portable `.gna` archives containing the
database, evidence, configuration, component versions, and recoverable master
key. GuardianNode adds an instance-only verification slot so it can verify the
finished archive without retaining the recovery private key.

Backups are written to a partial file, authenticated after creation, and then
subject to the configured retention count. The dashboard reports failed,
successful, verified, and restore-tested timestamps separately. A backup is
never marked verified unless its complete file inventory and evidence coverage
pass validation.
