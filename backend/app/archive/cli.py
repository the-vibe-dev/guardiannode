"""Offline command-line interface for GuardianNode archives."""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from app import settings as settings_mod
from app.archive import crypto
from app.archive.format import (
    ArchiveError,
    create_archive,
    extract_archive,
    inspect_archive,
    restore_archive,
    verify_archive,
)
from app.services import encryption


def _credential(args: argparse.Namespace) -> tuple[str | None, X25519PrivateKey | None, bytes | None]:
    passphrase = None
    if getattr(args, "passphrase", False):
        passphrase = getpass.getpass("Archive passphrase: ")
    private = crypto.load_private_key(args.identity) if getattr(args, "identity", None) else None
    master = encryption.get_master_key() if getattr(args, "instance_key", False) else None
    return passphrase, private, master


def _add_unlock(parser: argparse.ArgumentParser, *, instance: bool = True) -> None:
    parser.add_argument("--passphrase", action="store_true", help="prompt for archive passphrase")
    parser.add_argument("--identity", type=Path, help="X25519 recovery private key")
    if instance:
        parser.add_argument("--instance-key", action="store_true", help="use configured instance key")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="guardiannode-archive")
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="generate an offline recovery recipient key")
    keygen.add_argument("private_key", type=Path)
    keygen.add_argument("public_key", type=Path)
    inspect = commands.add_parser("inspect", help="show public archive metadata")
    inspect.add_argument("archive", type=Path)
    verify = commands.add_parser("verify", help="authenticate and verify an archive")
    verify.add_argument("archive", type=Path)
    _add_unlock(verify)
    extract = commands.add_parser("extract", help="verify and extract an archive")
    extract.add_argument("archive", type=Path)
    extract.add_argument("destination", type=Path)
    _add_unlock(extract)
    restore = commands.add_parser("restore", help="restore a portable archive to an empty data directory")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--target", type=Path, required=True)
    restore.add_argument("--dry-run", action="store_true")
    _add_unlock(restore, instance=False)
    create = commands.add_parser("create", help="create a complete archive from this instance")
    create.add_argument("destination", type=Path)
    create.add_argument("--mode", choices=["portable", "instance_snapshot"], default="portable")
    create.add_argument("--passphrase", action="store_true")
    create.add_argument("--recipient", type=Path, help="X25519 recovery public key")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "keygen":
            fingerprint = crypto.generate_recipient_key(args.private_key, args.public_key)
            result = {"private_key": str(args.private_key), "public_key": str(args.public_key), "fingerprint": fingerprint}
        elif args.command == "inspect":
            result = inspect_archive(args.archive)
        elif args.command == "create":
            passphrase = getpass.getpass("Archive passphrase: ") if args.passphrase else None
            if args.passphrase and passphrase != getpass.getpass("Confirm passphrase: "):
                raise ArchiveError("passphrases do not match")
            recipient = crypto.load_public_key(args.recipient) if args.recipient else None
            result = create_archive(
                args.destination, data_dir=settings_mod.settings.data_dir,
                db_url=settings_mod.settings.db_url_resolved, mode=args.mode,
                passphrase=passphrase, recipient_key=recipient,
            )
        else:
            passphrase, private, master = _credential(args)
            if args.command == "verify":
                result = verify_archive(args.archive, passphrase=passphrase, private_key=private, master_key=master)
            elif args.command == "extract":
                result = extract_archive(args.archive, args.destination, passphrase=passphrase, private_key=private, master_key=master)
            else:
                result = restore_archive(
                    args.archive, args.target, passphrase=passphrase,
                    private_key=private, dry_run=args.dry_run,
                )
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    except (ArchiveError, crypto.CryptoError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
