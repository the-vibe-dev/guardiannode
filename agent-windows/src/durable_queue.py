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


def _load_or_create_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError("invalid queue encryption key")
        return key
    key = AESGCM.generate_key(bit_length=256)
    _write_private(path, key)
    return key


def _encode_payload(payload: dict) -> bytes:
    data = dict(payload)
    data.pop("_queue_id", None)
    image_bytes = data.pop("image_bytes")
    data["image_bytes_b64"] = base64.b64encode(image_bytes).decode("ascii")
    data.setdefault("idempotency_key", uuid4().hex)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_payload(data: bytes) -> dict:
    payload = json.loads(data.decode("utf-8"))
    payload["image_bytes"] = base64.b64decode(payload.pop("image_bytes_b64"))
    return payload


class DurableScreenshotQueue:
    """Small single-consumer SQLite queue with encrypted payload blobs.

    The queue keeps the newest frames under configurable item/byte caps. A
    fetched item stays on disk until the sender explicitly acks or drops it, so
    a process crash during upload does not lose the frame.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        key_path: Path | None = None,
        max_items: int = 200,
        max_bytes: int = 256 * 1024 * 1024,
        max_age_seconds: int = 7 * 24 * 60 * 60,
    ):
        self.path = path or default_queue_path()
        self.key_path = key_path or default_key_path()
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.max_age_seconds = max_age_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key = _load_or_create_key(self.key_path)
        self._ready = asyncio.Event()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
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
                    last_error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_screenshot_queue_ready "
                "ON screenshot_queue(next_attempt_at, created_at)"
            )

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
            row = conn.execute(
                """
                SELECT item_id, payload_nonce, payload_ciphertext
                FROM screenshot_queue
                WHERE next_attempt_at <= ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
        if row is None:
            return None
        item_id, nonce, ciphertext = row
        payload = _decode_payload(AESGCM(self._key).decrypt(nonce, ciphertext, item_id.encode("ascii")))
        payload["_queue_id"] = item_id
        return payload

    def ack_payload(self, payload: dict) -> None:
        item_id = payload.get("_queue_id")
        if not item_id:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM screenshot_queue WHERE item_id = ?", (item_id,))

    def drop_payload(self, payload: dict, reason: str = "") -> None:
        self.ack_payload(payload)

    def retry_payload(self, payload: dict, *, delay_seconds: float, error: str = "") -> None:
        item_id = payload.get("_queue_id")
        if not item_id:
            self.put_nowait(payload)
            return
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE screenshot_queue
                SET attempts = attempts + 1,
                    next_attempt_at = ?,
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
                "SELECT item_id FROM screenshot_queue ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return
            conn.execute("DELETE FROM screenshot_queue WHERE item_id = ?", (row[0],))
