"""Create, inspect, verify, extract, and restore GuardianNode archives."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

from app import __version__
from app import settings as settings_mod
from app.archive import crypto
from app.archive.identity import identity_path, load_or_create
from app.db.maintenance import backup_database, database_schema_revision, sqlite_path_from_url
from app.services import encryption

FORMAT = "guardiannode-archive-v1"
MANIFEST_FORMAT = "guardiannode-archive-manifest-v1"
MAX_FILES = 100_000
MAX_MEMBER_SIZE = 8 * 1024 * 1024 * 1024


class ArchiveError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(crypto.canonical_json(value) + b"\n")


def _record_id(columns: list[str], row: sqlite3.Row) -> dict[str, Any]:
    return {name: row[name] for name in columns}


def _encoded_field(table: str, record_id: dict[str, Any], name: str, value: Any) -> Any:
    if not isinstance(value, bytes):
        return value
    encoded: dict[str, Any] = {"encoding": "base64", "value": base64.b64encode(value).decode()}
    if name.endswith("_enc") and len(value) >= 28:
        encoded["encryption"] = {
            "algorithm": "AES-256-GCM",
            "table": table,
            "record_id": record_id,
            "field": name,
            "nonce": base64.b64encode(value[:12]).decode(),
            "ciphertext": base64.b64encode(value[12:-16]).decode(),
            "tag": base64.b64encode(value[-16:]).decode(),
        }
    return encoded


def _write_logical_records(database: Path, records_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    records_dir.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        tables = [
            str(row[0]) for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            info = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            primary = [str(row[1]) for row in sorted(info, key=lambda item: int(item[5])) if row[5]]
            column_names = [str(row[1]) for row in info]
            count = 0
            with (records_dir / f"{table}.jsonl").open("wb") as output:
                for row in conn.execute(f"SELECT * FROM {quoted}"):
                    record_id = _record_id(primary, row) if primary else {"row_number": count}
                    payload = {
                        "record_id": record_id,
                        "fields": {
                            name: _encoded_field(table, record_id, name, row[name])
                            for name in column_names
                        },
                    }
                    output.write(crypto.canonical_json(payload) + b"\n")
                    count += 1
            counts[table] = count
    return counts


def _copy_evidence(
    data_dir: Path, payload: Path, database: Path
) -> tuple[int, int, dict[str, str]]:
    source = data_dir / "evidence"
    destination = payload / "evidence"
    count = total = 0
    destination.mkdir(parents=True)
    for path in source.rglob("*") if source.exists() else ():
        if path.is_symlink():
            raise ArchiveError(f"refusing symlink in evidence directory: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        count += 1
        total += target.stat().st_size
    archived = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*") if path.is_file()
    }
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_blobs'"
        ).fetchone()
        rows = conn.execute("SELECT blob_id, encrypted_path FROM evidence_blobs").fetchall() if has_table else []
    root = source.resolve()
    evidence_map: dict[str, str] = {}
    for blob_id, stored_path in rows:
        raw = Path(str(stored_path))
        candidate = raw if raw.is_absolute() else root / raw
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise ArchiveError(f"evidence path escapes the evidence directory: {blob_id}")
        relative_path = resolved.relative_to(root).as_posix()
        if relative_path not in archived:
            raise ArchiveError(f"database-referenced evidence is missing: {blob_id}")
        evidence_map[str(blob_id)] = relative_path
    return count, total, evidence_map


def _inventory(payload: Path) -> list[dict[str, Any]]:
    files = []
    for path in sorted(payload.rglob("*")):
        if path.is_file() and path.name not in {"manifest.json", "manifest.sig"}:
            files.append({
                "path": path.relative_to(payload).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            })
    return files


def _zip_payload(payload: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(payload).as_posix())


def create_archive(
    destination: Path, *, data_dir: Path, db_url: str, mode: str = "portable",
    passphrase: str | None = None, recipient_key: X25519PublicKey | None = None,
) -> dict[str, Any]:
    """Create a complete GNA v1 recovery archive."""
    if mode not in {"portable", "instance_snapshot"}:
        raise ArchiveError(f"unsupported archive mode: {mode}")
    if destination.exists():
        raise ArchiveError(f"refusing to overwrite archive: {destination}")
    if mode == "portable" and not passphrase and recipient_key is None:
        raise ArchiveError("portable archives require a passphrase or recipient public key")
    source_database = sqlite_path_from_url(db_url)
    identity = load_or_create(data_dir / "keys")
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive_key = os.urandom(32)
    slots = []
    if passphrase:
        slots.append(crypto.passphrase_slot(archive_key, passphrase))
    if recipient_key is not None:
        slots.append(crypto.recipient_slot(archive_key, recipient_key))
    if mode == "instance_snapshot":
        slots.append(crypto.instance_slot(archive_key, encryption.get_master_key()))

    with tempfile.TemporaryDirectory(prefix="guardiannode-archive-") as temporary:
        root = Path(temporary)
        payload = root / "payload"
        payload.mkdir()
        database = payload / "database.sqlite3"
        backup_database(database, source=source_database)
        # The database backup helper emits an adjacent implementation manifest;
        # GNA has its own complete signed manifest, so do not duplicate it.
        database.with_name(database.name + ".manifest.json").unlink(missing_ok=True)
        counts = _write_logical_records(database, payload / "records")
        evidence_count, evidence_bytes, evidence_map = _copy_evidence(data_dir, payload, database)
        _write_json(payload / "evidence-map.json", evidence_map)
        config = data_dir / "server.env"
        if config.is_file() and not config.is_symlink():
            config_target = payload / "configuration" / "server.env"
            config_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(config, config_target)
        identity_file = identity_path(data_dir / "keys")
        identity_target = payload / "key_material" / identity_file.name
        identity_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(identity_file, identity_target)
        if mode == "portable":
            key_path = payload / "key_material" / "master.key"
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(encryption.get_master_key())
        manifest = {
            "format": MANIFEST_FORMAT,
            "format_version": 1,
            "application_version": __version__,
            "schema_version": database_schema_revision(database),
            "export_timestamp": datetime.now(UTC).isoformat(),
            "export_mode": mode,
            "source_instance_identifier": identity.instance_id,
            "record_counts": counts,
            "evidence": {"covered": True, "file_count": evidence_count, "bytes": evidence_bytes},
            "encryption": {
                "payload": "AES-256-GCM-chunked",
                "database_fields": "AES-256-GCM where marked in logical records",
            },
            "key_wrapping": [slot["type"] for slot in slots],
            "component_versions": {
                "application": __version__,
                "rules": settings_mod.settings.rules_version,
                "text_model": settings_mod.settings.text_model,
                "vision_model": settings_mod.settings.vision_model,
                "policy_schema": 1,
            },
            "files": _inventory(payload),
        }
        manifest_bytes = crypto.canonical_json(manifest)
        (payload / "manifest.json").write_bytes(manifest_bytes)
        signature = identity.private_key.sign(manifest_bytes)
        _write_json(payload / "manifest.sig", {
            "algorithm": "Ed25519",
            "public_key": base64.b64encode(identity.public_bytes).decode(),
            "fingerprint": identity.fingerprint,
            "signature": base64.b64encode(signature).decode(),
        })
        zip_path = root / "payload.zip"
        _zip_payload(payload, zip_path)
        header = {
            "format": FORMAT,
            "format_version": 1,
            "application_version": __version__,
            "schema_version": manifest["schema_version"],
            "created_at": manifest["export_timestamp"],
            "mode": mode,
            "source_instance_identifier": identity.instance_id,
            "cipher": "AES-256-GCM-chunked",
            "key_slots": slots,
        }
        crypto.encrypt_file(zip_path, destination, header, archive_key)
    return {**header, "path": str(destination), "size": destination.stat().st_size}


def inspect_archive(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            header, _ = crypto.read_header(stream)
    except (OSError, crypto.CryptoError) as exc:
        raise ArchiveError(str(exc)) from exc
    if header.get("format") != FORMAT or header.get("format_version") != 1:
        raise ArchiveError("unsupported GuardianNode archive version")
    return header


def _unlock(
    header: dict[str, Any], *, passphrase: str | None,
    private_key: X25519PrivateKey | None, master_key: bytes | None,
) -> bytes:
    errors = []
    for slot in header.get("key_slots", []):
        try:
            return crypto.unwrap_slot(
                slot, passphrase=passphrase, private_key=private_key, master_key=master_key
            )
        except crypto.CryptoError as exc:
            errors.append(str(exc))
    raise ArchiveError("unable to unlock archive: " + "; ".join(errors or ["no key slots"]))


def _safe_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = zf.infolist()
    if len(members) > MAX_FILES:
        raise ArchiveError("archive contains too many files")
    seen: set[str] = set()
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ArchiveError(f"unsafe archive path: {member.filename}")
        if member.filename in seen:
            raise ArchiveError(f"duplicate archive path: {member.filename}")
        seen.add(member.filename)
        if member.file_size > MAX_MEMBER_SIZE:
            raise ArchiveError(f"archive member is too large: {member.filename}")
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise ArchiveError(f"archive links are not allowed: {member.filename}")
    return members


def _extract_validated(zip_path: Path, destination: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as zf:
        members = _safe_members(zf)
        zf.extractall(destination, members=members)
    try:
        manifest_bytes = (destination / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        signature = json.loads((destination / "manifest.sig").read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ArchiveError("archive manifest is missing or invalid") from exc
    if crypto.canonical_json(manifest) != manifest_bytes:
        raise ArchiveError("archive manifest is not canonical")
    if manifest.get("format") != MANIFEST_FORMAT or manifest.get("format_version") != 1:
        raise ArchiveError("unsupported archive manifest")
    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(signature["public_key"]))
        public.verify(base64.b64decode(signature["signature"]), manifest_bytes)
        public_raw = base64.b64decode(signature["public_key"])
        if hashlib.sha256(public_raw).hexdigest() != signature["fingerprint"]:
            raise ArchiveError("archive signer fingerprint does not match its public key")
    except (InvalidSignature, KeyError, TypeError, ValueError) as exc:
        raise ArchiveError("archive manifest signature is invalid") from exc
    expected_paths = {entry["path"] for entry in manifest.get("files", [])}
    actual_paths = {
        path.relative_to(destination).as_posix() for path in destination.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "manifest.sig"}
    }
    if actual_paths != expected_paths:
        raise ArchiveError("archive file inventory does not match payload")
    for entry in manifest["files"]:
        path = destination / PurePosixPath(entry["path"])
        if path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
            raise ArchiveError(f"archive file failed integrity verification: {entry['path']}")
    return {"manifest": manifest, "signer": signature}


def verify_archive(
    path: Path, *, passphrase: str | None = None,
    private_key: X25519PrivateKey | None = None, master_key: bytes | None = None,
) -> dict[str, Any]:
    header = inspect_archive(path)
    key = _unlock(header, passphrase=passphrase, private_key=private_key, master_key=master_key)
    with tempfile.TemporaryDirectory(prefix="guardiannode-verify-") as temporary:
        root = Path(temporary)
        zip_path = root / "payload.zip"
        try:
            crypto.decrypt_file(path, zip_path, key)
            result = _extract_validated(zip_path, root / "payload")
        except (OSError, zipfile.BadZipFile, crypto.CryptoError) as exc:
            raise ArchiveError(str(exc)) from exc
    return {"ok": True, "header": header, **result}


def extract_archive(
    path: Path, destination: Path, *, passphrase: str | None = None,
    private_key: X25519PrivateKey | None = None, master_key: bytes | None = None,
) -> dict[str, Any]:
    if destination.exists():
        raise ArchiveError(f"refusing to overwrite extraction target: {destination}")
    header = inspect_archive(path)
    key = _unlock(header, passphrase=passphrase, private_key=private_key, master_key=master_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.partial")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    zip_path = staging.with_name(f".{destination.name}.payload.partial.zip")
    try:
        crypto.decrypt_file(path, zip_path, key)
        result = _extract_validated(zip_path, staging)
        zip_path.unlink()
        os.replace(staging, destination)
        return {"ok": True, "header": header, **result, "destination": str(destination)}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        raise


def restore_archive(
    path: Path, target: Path, *, passphrase: str | None = None,
    private_key: X25519PrivateKey | None = None, dry_run: bool = False,
) -> dict[str, Any]:
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ArchiveError("restore target must be an empty directory")
    with tempfile.TemporaryDirectory(prefix="guardiannode-restore-") as temporary:
        extracted = Path(temporary) / "archive"
        result = extract_archive(path, extracted, passphrase=passphrase, private_key=private_key)
        manifest = result["manifest"]
        if manifest.get("export_mode") != "portable":
            raise ArchiveError("clean-host restore requires a portable archive")
        database = extracted / "database.sqlite3"
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as conn:
            integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise ArchiveError("restored database failed SQLite integrity check")
        if dry_run:
            return {"ok": True, "dry_run": True, "manifest": manifest}
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(f".{target.name}.restore.partial")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        try:
            restored_database = staging / "guardiannode.db"
            shutil.copy2(database, restored_database)
            evidence_map = json.loads((extracted / "evidence-map.json").read_text("utf-8"))
            with closing(sqlite3.connect(restored_database)) as conn:
                for blob_id, relative_path in evidence_map.items():
                    conn.execute(
                        "UPDATE evidence_blobs SET encrypted_path=? WHERE blob_id=?",
                        (relative_path, blob_id),
                    )
                conn.commit()
            for directory in ("evidence", "configuration", "key_material"):
                source = extracted / directory
                if source.exists():
                    destination = staging / ("keys" if directory == "key_material" else directory)
                    shutil.copytree(source, destination, dirs_exist_ok=True)
            server_env = staging / "configuration" / "server.env"
            if server_env.exists():
                shutil.copy2(server_env, staging / "server.env")
            for directory_path in (staging, staging / "keys", staging / "evidence"):
                if os.name != "nt" and directory_path.exists():
                    os.chmod(directory_path, 0o700)
            if target.exists():
                target.rmdir()
            os.replace(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return {"ok": True, "dry_run": False, "target": str(target), "manifest": manifest}
