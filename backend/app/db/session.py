"""SQLAlchemy engine + session factory."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import settings as settings_mod

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def configure_sqlite_engine(engine: Engine) -> Engine:
    """Apply SQLite integrity and durability pragmas to every DB-API connection."""
    if engine.dialect.name != "sqlite":
        return engine

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    return engine


def get_engine():
    global _engine
    if _engine is None:
        settings = settings_mod.settings
        settings.ensure_dirs()
        url = settings.db_url_resolved
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = configure_sqlite_engine(create_engine(url, connect_args=connect_args, future=True))
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)
    return _SessionLocal


def begin_immediate_if_sqlite(session: Session) -> None:
    """Acquire SQLite's write lock before read-check-write state transitions.

    Setup and pairing both need "look up current state, then insert/update" to
    be atomic under concurrent HTTP requests. SQLite's default deferred
    transactions let two requests observe the same pre-write state; BEGIN
    IMMEDIATE serializes those flows for the default deployment.
    """
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))


@contextmanager
def session_scope() -> Iterator[Session]:
    s = get_sessionmaker()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    s = get_sessionmaker()()
    try:
        yield s
    finally:
        s.close()
