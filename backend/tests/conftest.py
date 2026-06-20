"""Pytest fixtures: throwaway data dir + in-memory backend."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_data_dir(monkeypatch, tmp_path: Path) -> Iterator[Path]:
    """Point GUARDIANNODE_DATA_DIR at a temp dir for each test."""
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    # Reload settings so the env var takes effect.
    from app import settings as settings_mod
    settings_mod.settings = settings_mod.Settings()
    # Reset encryption cache so a fresh master key is generated per test.
    from app.services import encryption
    encryption._reset_cache()
    # Reset the cached DB engine so each test gets its own database file.
    from app.db import session as session_mod
    session_mod._engine = None
    session_mod._SessionLocal = None
    yield tmp_path


@pytest.fixture
def db_session():
    """In-memory SQLite session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base
    from app.db.session import configure_sqlite_engine

    engine = configure_sqlite_engine(create_engine("sqlite:///:memory:", future=True))
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = session_local()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
