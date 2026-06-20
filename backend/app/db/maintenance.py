"""SQLite maintenance commands: integrity check, backup, and restore."""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from app import settings as settings_mod


class DatabaseMaintenanceError(RuntimeError):
    """Raised when a maintenance operation cannot be completed safely."""


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    messages: list[str]


def sqlite_path_from_url(db_url: str) -> Path:
    url = make_url(db_url)
    if url.drivername not in {"sqlite", "sqlite+pysqlite"}:
        raise DatabaseMaintenanceError("Database maintenance commands currently support SQLite only")
    if not url.database or url.database == ":memory:":
        raise DatabaseMaintenanceError("A file-backed SQLite database is required")
    return Path(url.database)


def configured_sqlite_path() -> Path:
    return sqlite_path_from_url(settings_mod.settings.db_url_resolved)


def integrity_check(path: Path | None = None) -> IntegrityResult:
    db_path = path or configured_sqlite_path()
    if not db_path.is_file():
        raise DatabaseMaintenanceError(f"SQLite database not found: {db_path}")
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = [str(row[0]) for row in conn.execute("PRAGMA integrity_check").fetchall()]
    return IntegrityResult(ok=rows == ["ok"], messages=rows)


def _fsync_file(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _quarantine_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    root = path.parent / ".ignored-cleanup"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex}-{path.name}"
    return path.replace(target)


def backup_database(destination: Path, *, source: Path | None = None, overwrite: bool = False) -> Path:
    source_path = source or configured_sqlite_path()
    if not source_path.is_file():
        raise DatabaseMaintenanceError(f"SQLite database not found: {source_path}")
    source_result = integrity_check(source_path)
    if not source_result.ok:
        raise DatabaseMaintenanceError(
            "Source database failed integrity check: " + "; ".join(source_result.messages)
        )

    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise DatabaseMaintenanceError(f"Backup already exists: {destination}")
    tmp_path = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
    try:
        with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as src:
            with sqlite3.connect(tmp_path) as dst:
                src.backup(dst)
                dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        result = integrity_check(tmp_path)
        if not result.ok:
            raise DatabaseMaintenanceError(
                "Backup failed integrity check: " + "; ".join(result.messages)
            )
        _fsync_file(tmp_path)
        os.replace(tmp_path, destination)
        if os.name != "nt":
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
        _fsync_dir(destination.parent)
    except Exception:
        _quarantine_file(tmp_path)
        raise
    return destination


def restore_database(backup: Path, *, destination: Path | None = None) -> Path:
    backup = backup.expanduser()
    if not backup.is_file():
        raise DatabaseMaintenanceError(f"Backup not found: {backup}")
    backup_result = integrity_check(backup)
    if not backup_result.ok:
        raise DatabaseMaintenanceError(
            "Backup failed integrity check: " + "; ".join(backup_result.messages)
        )

    destination_path = (destination or configured_sqlite_path()).expanduser()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination_path.with_name(f".{destination_path.name}.{uuid4().hex}.restore")
    replaced_path: Path | None = None
    try:
        with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as src:
            with sqlite3.connect(tmp_path) as dst:
                src.backup(dst)
        result = integrity_check(tmp_path)
        if not result.ok:
            raise DatabaseMaintenanceError(
                "Restored database failed integrity check: " + "; ".join(result.messages)
            )
        _fsync_file(tmp_path)
        if destination_path.exists():
            restore_root = destination_path.parent / "backups"
            restore_root.mkdir(parents=True, exist_ok=True)
            replaced_path = restore_root / (
                f"pre-restore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-"
                f"{uuid4().hex}-{destination_path.name}"
            )
            destination_path.replace(replaced_path)
        for suffix in ("-wal", "-shm"):
            _quarantine_file(destination_path.with_name(destination_path.name + suffix))
        os.replace(tmp_path, destination_path)
        if os.name != "nt":
            try:
                os.chmod(destination_path, 0o600)
            except OSError:
                pass
        _fsync_dir(destination_path.parent)
    except Exception:
        _quarantine_file(tmp_path)
        if replaced_path is not None and replaced_path.exists() and not destination_path.exists():
            shutil.move(str(replaced_path), str(destination_path))
        raise
    return destination_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="guardiannode-db")
    subcommands = parser.add_subparsers(dest="command", required=True)

    integrity = subcommands.add_parser("integrity", help="Run PRAGMA integrity_check")
    integrity.add_argument("--database", type=Path, help="SQLite database path")

    backup = subcommands.add_parser("backup", help="Create an atomic SQLite backup")
    backup.add_argument("destination", type=Path)
    backup.add_argument("--database", type=Path, help="SQLite database path")
    backup.add_argument("--overwrite", action="store_true", help="Replace an existing backup file")

    restore = subcommands.add_parser("restore", help="Restore a SQLite backup")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--database", type=Path, help="SQLite database path to replace")
    return parser


def cli(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "integrity":
            result = integrity_check(args.database)
            for message in result.messages:
                print(message)
            return 0 if result.ok else 2
        if args.command == "backup":
            path = backup_database(args.destination, source=args.database, overwrite=args.overwrite)
            print(path)
            return 0
        if args.command == "restore":
            path = restore_database(args.backup, destination=args.database)
            print(path)
            return 0
    except DatabaseMaintenanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli())
