"""Create, inspect, verify, extract, and restore GuardianNode archives."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import time
import unicodedata
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

FORMAT = "guardiannode-archive-v2"
MANIFEST_FORMAT = "guardiannode-archive-manifest-v2"
MAX_FILES = 100_000
MAX_MEMBER_SIZE = 2 * 1024 * 1024 * 1024
MAX_TOTAL_SIZE = 12 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_EVENT_RECORDS = 1_000_000
MAX_VALIDATION_SECONDS = 30 * 60
MAX_MANIFEST_SIZE = 64 * 1024 * 1024
MAX_SIGNATURE_SIZE = 64 * 1024

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
    *(f"COM{number}" for number in "¹²³"),
    *(f"LPT{number}" for number in "¹²³"),
}
_WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"\\|?*')


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
                where = ""
                if "deletion_state" in column_names and table in {"events", "evidence_blobs"}:
                    where = " WHERE deletion_state = 'active'"
                for row in conn.execute(f"SELECT * FROM {quoted}{where}"):
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
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_blobs'"
        ).fetchone()
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(evidence_blobs)").fetchall()
        } if has_table else set()
        where = " WHERE deletion_state = 'active'" if "deletion_state" in columns else ""
        rows = conn.execute(
            f"SELECT blob_id, encrypted_path FROM evidence_blobs{where}"
        ).fetchall() if has_table else []
    root = source.resolve()
    evidence_map: dict[str, str] = {}
    for blob_id, stored_path in rows:
        raw = Path(str(stored_path))
        candidate = raw if raw.is_absolute() else root / raw
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise ArchiveError(f"evidence path escapes the evidence directory: {blob_id}")
        relative_path = resolved.relative_to(root).as_posix()
        probe = candidate
        while probe != root:
            if probe.is_symlink():
                raise ArchiveError(f"database-referenced evidence uses a symlink: {blob_id}")
            probe = probe.parent
        if not resolved.is_file():
            raise ArchiveError(f"database-referenced evidence is missing: {blob_id}")
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resolved, target)
        count += 1
        total += target.stat().st_size
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
    include_instance_key_slot: bool = False,
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
    if mode == "instance_snapshot" or include_instance_key_slot:
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
            "format_version": 2,
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
            "format_version": 2,
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
    if header.get("format") != FORMAT or header.get("format_version") != 2:
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


def _validated_member_path(name: str) -> PurePosixPath:
    """Return one canonical archive-relative path safe on POSIX and Windows."""
    raw = name[:-1] if name.endswith("/") else name
    if not raw or "\x00" in raw or "\\" in raw:
        raise ArchiveError(f"unsafe archive path: {name}")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or path.as_posix() != raw:
        raise ArchiveError(f"unsafe archive path: {name}")
    for part in path.parts:
        if part in {"", ".", ".."} or part.endswith((".", " ")):
            raise ArchiveError(f"unsafe archive path: {name}")
        if any(ord(char) < 32 or char in _WINDOWS_FORBIDDEN_CHARS for char in part):
            raise ArchiveError(f"unsafe archive path: {name}")
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            raise ArchiveError(f"unsafe archive path: {name}")
    return path


def _portable_path_key(path: PurePosixPath) -> str:
    """Windows-safe collision key for otherwise canonical member paths."""
    return unicodedata.normalize("NFC", path.as_posix()).casefold()


def _safe_member_target(root: Path, name: str) -> Path:
    """Resolve a validated member under root immediately before filesystem use."""
    relative = _validated_member_path(name)
    native = root.joinpath(*relative.parts)
    probe = native
    while probe != root:
        if probe.is_symlink():
            raise ArchiveError(f"archive path uses a symlink: {name}")
        probe = probe.parent
    target = native.resolve(strict=False)
    if target == root or not target.is_relative_to(root):
        raise ArchiveError(f"archive path escapes extraction target: {name}")
    return target


def _safe_members(zf: zipfile.ZipFile, *, deadline: float) -> list[zipfile.ZipInfo]:
    members = zf.infolist()
    if len(members) > MAX_FILES:
        raise ArchiveError("archive contains too many files")
    seen: dict[str, str] = {}
    total_size = 0
    for member in members:
        if time.monotonic() > deadline:
            raise ArchiveError("archive validation time budget exceeded")
        path = _validated_member_path(member.filename)
        key = _portable_path_key(path)
        if key in seen:
            raise ArchiveError(
                f"duplicate or non-portable archive path: {member.filename} conflicts with {seen[key]}"
            )
        seen[key] = member.filename
        if member.file_size > MAX_MEMBER_SIZE:
            raise ArchiveError(f"archive member is too large: {member.filename}")
        total_size += member.file_size
        if total_size > MAX_TOTAL_SIZE:
            raise ArchiveError("archive aggregate expansion is too large")
        if member.file_size > 1024 * 1024:
            if member.compress_size <= 0 or member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
                raise ArchiveError(f"archive member compression ratio is too high: {member.filename}")
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise ArchiveError(f"archive links are not allowed: {member.filename}")
    return members


def _read_bounded_member(
    zf: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    *,
    limit: int,
    label: str,
    deadline: float,
) -> bytes:
    if member.is_dir() or member.file_size > limit:
        raise ArchiveError(f"archive {label} is too large or invalid")
    if time.monotonic() > deadline:
        raise ArchiveError("archive validation time budget exceeded")
    with zf.open(member, "r") as source:
        value = source.read(limit + 1)
    if len(value) > limit or len(value) != member.file_size:
        raise ArchiveError(f"archive {label} is too large or invalid")
    return value


def _authenticate_manifest(
    zf: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    *,
    deadline: float,
    trusted_signer: Ed25519PublicKey | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_path = {_validated_member_path(member.filename).as_posix(): member for member in members}
    try:
        manifest_member = by_path["manifest.json"]
        signature_member = by_path["manifest.sig"]
    except KeyError as exc:
        raise ArchiveError("archive manifest is missing or invalid") from exc
    manifest_bytes = _read_bounded_member(
        zf,
        manifest_member,
        limit=MAX_MANIFEST_SIZE,
        label="manifest",
        deadline=deadline,
    )
    signature_bytes = _read_bounded_member(
        zf,
        signature_member,
        limit=MAX_SIGNATURE_SIZE,
        label="signature",
        deadline=deadline,
    )
    try:
        manifest = json.loads(manifest_bytes)
        signature = json.loads(signature_bytes)
    except (TypeError, ValueError) as exc:
        raise ArchiveError("archive manifest is missing or invalid") from exc
    if not isinstance(manifest, dict) or not isinstance(signature, dict):
        raise ArchiveError("archive manifest is missing or invalid")
    if crypto.canonical_json(manifest) != manifest_bytes:
        raise ArchiveError("archive manifest is not canonical")
    if manifest.get("format") != MANIFEST_FORMAT or manifest.get("format_version") != 2:
        raise ArchiveError("unsupported archive manifest")
    try:
        if signature.get("algorithm") != "Ed25519":
            raise ValueError("unsupported signature algorithm")
        public_raw = base64.b64decode(signature["public_key"], validate=True)
        signed_value = base64.b64decode(signature["signature"], validate=True)
        public = Ed25519PublicKey.from_public_bytes(public_raw)
        public.verify(signed_value, manifest_bytes)
        fingerprint = hashlib.sha256(public_raw).hexdigest()
        if not secrets.compare_digest(fingerprint, str(signature["fingerprint"])):
            raise ArchiveError("archive signer fingerprint does not match its public key")
        if trusted_signer is not None:
            trusted_raw = trusted_signer.public_bytes_raw()
            if not secrets.compare_digest(public_raw, trusted_raw):
                raise ArchiveError("archive signer is not the enrolled recovery signer")
    except (InvalidSignature, KeyError, TypeError, ValueError) as exc:
        raise ArchiveError("archive manifest signature is invalid") from exc
    return manifest, signature


def _extract_validated(
    zip_path: Path,
    destination: Path,
    *,
    trusted_signer: Ed25519PublicKey | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_VALIDATION_SECONDS
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve(strict=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = _safe_members(zf, deadline=deadline)
        manifest, signature = _authenticate_manifest(
            zf,
            members,
            deadline=deadline,
            trusted_signer=trusted_signer,
        )
        extracted_total = 0
        for member in members:
            target = _safe_member_target(root, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(member, "r") as source, target.open("xb") as output:
                while True:
                    if time.monotonic() > deadline:
                        raise ArchiveError("archive validation time budget exceeded")
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    extracted_total += len(chunk)
                    if written > member.file_size or extracted_total > MAX_TOTAL_SIZE:
                        raise ArchiveError("archive expanded beyond its declared bounds")
                    output.write(chunk)
            if written != member.file_size:
                raise ArchiveError(f"archive member size changed during extraction: {member.filename}")
    files = manifest.get("files")
    if not isinstance(files, list) or any(not isinstance(entry, dict) for entry in files):
        raise ArchiveError("archive manifest file inventory is invalid")
    try:
        expected_paths = {_validated_member_path(str(entry["path"])).as_posix() for entry in files}
    except KeyError as exc:
        raise ArchiveError("archive manifest file inventory is invalid") from exc
    if len(expected_paths) != len(files):
        raise ArchiveError("archive manifest contains duplicate file paths")
    if int(manifest.get("record_counts", {}).get("events", 0)) > MAX_EVENT_RECORDS:
        raise ArchiveError("archive contains too many event records")
    actual_paths = {
        path.relative_to(destination).as_posix() for path in destination.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "manifest.sig"}
    }
    if actual_paths != expected_paths:
        raise ArchiveError("archive file inventory does not match payload")
    for entry in files:
        member_path = str(entry["path"])
        path = _safe_member_target(root, member_path)
        try:
            matches = path.stat().st_size == int(entry["size"]) and _sha256(path) == entry["sha256"]
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise ArchiveError(f"archive file inventory is invalid: {member_path}") from exc
        if not matches:
            raise ArchiveError(f"archive file failed integrity verification: {member_path}")
    return {"manifest": manifest, "signer": signature}


def verify_archive(
    path: Path, *, passphrase: str | None = None,
    private_key: X25519PrivateKey | None = None, master_key: bytes | None = None,
    trusted_signer: Ed25519PublicKey | None = None,
) -> dict[str, Any]:
    header = inspect_archive(path)
    key = _unlock(header, passphrase=passphrase, private_key=private_key, master_key=master_key)
    with tempfile.TemporaryDirectory(prefix="guardiannode-verify-") as temporary:
        root = Path(temporary)
        zip_path = root / "payload.zip"
        try:
            crypto.decrypt_file(path, zip_path, key)
            result = _extract_validated(zip_path, root / "payload", trusted_signer=trusted_signer)
        except (OSError, zipfile.BadZipFile, crypto.CryptoError) as exc:
            raise ArchiveError(str(exc)) from exc
    return {"ok": True, "header": header, **result}


def extract_archive(
    path: Path, destination: Path, *, passphrase: str | None = None,
    private_key: X25519PrivateKey | None = None, master_key: bytes | None = None,
    trusted_signer: Ed25519PublicKey | None = None,
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
        result = _extract_validated(zip_path, staging, trusted_signer=trusted_signer)
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
    trusted_signer: Ed25519PublicKey | None = None,
) -> dict[str, Any]:
    if trusted_signer is None:
        raise ArchiveError("restore requires an enrolled recovery signer public key")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ArchiveError("restore target must be an empty directory")
    with tempfile.TemporaryDirectory(prefix="guardiannode-restore-") as temporary:
        extracted = Path(temporary) / "archive"
        result = extract_archive(
            path,
            extracted,
            passphrase=passphrase,
            private_key=private_key,
            trusted_signer=trusted_signer,
        )
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
                # Restored active state is quarantined. A parent must explicitly
                # re-pair devices and re-enable every integration on the new host.
                conn.execute(
                    "UPDATE devices SET paired=0, token_hash=NULL, status='re_pair_required'"
                )
                conn.execute(
                    "UPDATE users SET session_revoked_at=?",
                    (datetime.now(UTC).isoformat(),),
                )
                conn.execute("UPDATE pairing_codes SET used=1")
                conn.execute("UPDATE notification_jobs SET status='cancelled'")
                for key in ("notification_settings", "complete_backup_config"):
                    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                    if row:
                        try:
                            config = json.loads(row[0])
                        except (TypeError, ValueError):
                            config = {}
                        config["enabled"] = False
                        for secret_key in (
                            "password_enc", "smtp_password", "webhook_url", "hook_argv",
                            "recipient_public_key",
                        ):
                            config.pop(secret_key, None)
                        conn.execute(
                            "UPDATE settings SET value=? WHERE key=?",
                            (json.dumps(config, sort_keys=True), key),
                        )
                conn.commit()
            for directory in ("evidence", "key_material"):
                source = extracted / directory
                if source.exists():
                    destination = staging / ("keys" if directory == "key_material" else directory)
                    shutil.copytree(source, destination, dirs_exist_ok=True)
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
