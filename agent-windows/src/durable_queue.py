"""Durable encrypted screenshot queue for backend outages."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def default_queue_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "GuardianNode" / "AgentSecure"
    else:
        base = Path.home() / ".guardiannode" / "AgentSecure"
    return base / "queue.sqlite"


def default_key_path() -> Path:
    return default_queue_path().parent / "queue.key"


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            fd = -1
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _read_existing_key(path: Path, *, timeout_seconds: float = 1.0) -> bytes:
    deadline = time.monotonic() + timeout_seconds
    while True:
        key = path.read_bytes()
        if len(key) == 32:
            return key
        if time.monotonic() >= deadline:
            raise ValueError("invalid queue encryption key")
        time.sleep(0.01)


def _load_or_create_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return _read_existing_key(path)
    key = AESGCM.generate_key(bit_length=256)
    try:
        _write_private(path, key)
        return key
    except FileExistsError:
        # Another process won the first-run race. Reopen and validate the
        # winner so concurrent session agents converge on one queue key.
        return _read_existing_key(path)


def _encode_payload(payload: dict) -> bytes:
    data = dict(payload)
    data.pop("_queue_id", None)
    data.pop("_queue_lease_owner", None)
    image_bytes = data.pop("image_bytes")
    data["image_bytes_b64"] = base64.b64encode(image_bytes).decode("ascii")
    data.setdefault("idempotency_key", uuid4().hex)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_payload(data: bytes) -> dict:
    payload = json.loads(data.decode("utf-8"))
    payload["image_bytes"] = base64.b64decode(payload.pop("image_bytes_b64"))
    return payload


class DurableScreenshotQueue:
    """Small SQLite queue with encrypted payload blobs and leased claims.

    The queue keeps the newest frames under configurable item/byte caps. A
    fetched item stays on disk and is leased to the claiming worker until the
    sender explicitly acks, drops, retries, or the lease expires, so a process
    crash during upload does not lose the frame or let live workers duplicate it.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        key_path: Path | None = None,
        max_items: int = 200,
        max_bytes: int = 256 * 1024 * 1024,
        max_age_seconds: int = 7 * 24 * 60 * 60,
        lease_seconds: float = 120.0,
    ):
        self.path = path or default_queue_path()
        self.key_path = key_path or default_key_path()
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.max_age_seconds = max_age_seconds
        self.lease_seconds = max(1.0, lease_seconds)
        self.lease_owner = f"{os.getpid()}-{uuid4().hex}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key = _load_or_create_key(self.key_path)
        self._ready = asyncio.Event()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.execute("PRAGMA busy_timeout=30000")
        deadline = time.monotonic() + 5.0
        while True:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                    conn.close()
                    raise
                time.sleep(0.05)
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS screenshot_queue (
                    item_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    payload_size INTEGER NOT NULL,
                    payload_nonce BLOB NOT NULL,
                    payload_ciphertext BLOB NOT NULL,
                    lease_owner TEXT,
                    lease_until REAL NOT NULL DEFAULT 0,
                    claimed_at REAL,
                    last_error TEXT
                )
                """
            )
            self._ensure_column(conn, "lease_owner", "TEXT")
            self._ensure_column(conn, "lease_until", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "claimed_at", "REAL")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_screenshot_queue_ready "
                "ON screenshot_queue(next_attempt_at, lease_until, created_at)"
            )

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, name: str, ddl: str) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(screenshot_queue)")}
        if name not in columns:
            conn.execute(f"ALTER TABLE screenshot_queue ADD COLUMN {name} {ddl}")

    def put_nowait(self, payload: dict) -> None:
        plain = _encode_payload(payload)
        if len(plain) > self.max_bytes:
            raise asyncio.QueueFull
        item_id = uuid4().hex
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, plain, item_id.encode("ascii"))
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO screenshot_queue (
                    item_id, created_at, next_attempt_at, attempts,
                    payload_size, payload_nonce, payload_ciphertext
                ) VALUES (?, ?, 0, 0, ?, ?, ?)
                """,
                (item_id, now, len(plain), nonce, ciphertext),
            )
            self._enforce_limits(conn)
        self._ready.set()

    async def get(self) -> dict:
        while True:
            item = self._get_ready()
            if item is not None:
                return item
            self._ready.clear()
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=1.0)
            except TimeoutError:
                continue

    def _get_ready(self) -> dict | None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT item_id
                FROM screenshot_queue
                WHERE next_attempt_at <= ?
                  AND (lease_owner IS NULL OR lease_until <= ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (now, now),
            ).fetchone()
            if row is None:
                return None
            item_id = row[0]
            lease_until = now + self.lease_seconds
            updated = conn.execute(
                """
                UPDATE screenshot_queue
                SET lease_owner = ?, lease_until = ?, claimed_at = ?
                WHERE item_id = ?
                  AND next_attempt_at <= ?
                  AND (lease_owner IS NULL OR lease_until <= ?)
                """,
                (self.lease_owner, lease_until, now, item_id, now, now),
            ).rowcount
            if updated != 1:
                return None
            row = conn.execute(
                """
                SELECT item_id, payload_nonce, payload_ciphertext
                FROM screenshot_queue
                WHERE item_id = ? AND lease_owner = ?
                """,
                (item_id, self.lease_owner),
            ).fetchone()
        if row is None:
            return None
        item_id, nonce, ciphertext = row
        payload = _decode_payload(AESGCM(self._key).decrypt(nonce, ciphertext, item_id.encode("ascii")))
        payload["_queue_id"] = item_id
        payload["_queue_lease_owner"] = self.lease_owner
        return payload

    def ack_payload(self, payload: dict) -> None:
        item_id = payload.get("_queue_id")
        lease_owner = payload.get("_queue_lease_owner")
        if not item_id:
            return
        with self._connect() as conn:
            if lease_owner:
                conn.execute(
                    "DELETE FROM screenshot_queue WHERE item_id = ? AND lease_owner = ?",
                    (item_id, lease_owner),
                )
            else:
                conn.execute("DELETE FROM screenshot_queue WHERE item_id = ?", (item_id,))

    def drop_payload(self, payload: dict, reason: str = "") -> None:
        self.ack_payload(payload)

    def retry_payload(self, payload: dict, *, delay_seconds: float, error: str = "") -> None:
        item_id = payload.get("_queue_id")
        lease_owner = payload.get("_queue_lease_owner")
        if not item_id:
            self.put_nowait(payload)
            return
        with self._connect() as conn:
            if lease_owner:
                conn.execute(
                    """
                    UPDATE screenshot_queue
                    SET attempts = attempts + 1,
                        next_attempt_at = ?,
                        lease_owner = NULL,
                        lease_until = 0,
                        claimed_at = NULL,
                        last_error = ?
                    WHERE item_id = ? AND lease_owner = ?
                    """,
                    (time.time() + max(0.0, delay_seconds), error[:500], item_id, lease_owner),
                )
            else:
                conn.execute(
                    """
                    UPDATE screenshot_queue
                    SET attempts = attempts + 1,
                        next_attempt_at = ?,
                        lease_owner = NULL,
                        lease_until = 0,
                        claimed_at = NULL,
                        last_error = ?
                    WHERE item_id = ?
                    """,
                    (time.time() + max(0.0, delay_seconds), error[:500], item_id),
                )
        self._ready.set()

    def qsize(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT count(*) FROM screenshot_queue").fetchone()[0])

    def full(self) -> bool:
        return self.qsize() >= self.max_items

    def task_done(self) -> None:
        return None

    def _enforce_limits(self, conn: sqlite3.Connection) -> None:
        cutoff = time.time() - self.max_age_seconds if self.max_age_seconds > 0 else 0
        if cutoff:
            conn.execute("DELETE FROM screenshot_queue WHERE created_at < ?", (cutoff,))
        while True:
            count, total = conn.execute(
                "SELECT count(*), coalesce(sum(payload_size), 0) FROM screenshot_queue"
            ).fetchone()
            if count <= self.max_items and total <= self.max_bytes:
                return
            row = conn.execute(
                """
                SELECT item_id FROM screenshot_queue
                ORDER BY
                    CASE WHEN lease_owner IS NULL OR lease_until <= ? THEN 0 ELSE 1 END,
                    created_at ASC
                LIMIT 1
                """,
                (time.time(),),
            ).fetchone()
            if row is None:
                return
            conn.execute("DELETE FROM screenshot_queue WHERE item_id = ?", (row[0],))
