"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import secrets
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api import (
    alerts as alerts_api,
    audit as audit_api,
    auth as auth_api,
    child_requests as child_requests_api,
    dashboard as dashboard_api,
    devices as devices_api,
    events as events_api,
    health as health_api,
    models as models_api,
    policies as policies_api,
    profiles as profiles_api,
    risks as risks_api,
    setup as setup_api,
    settings as settings_api,
    storage as storage_api,
)
from app.db.models import Base
from app.db.session import get_engine
from app.services import mdns_advertiser
from app.settings import settings
from app.workers import cleanup_worker

log = logging.getLogger("guardiannode")


def _ensure_session_secret() -> str:
    if settings.session_secret:
        return settings.session_secret
    settings.ensure_dirs()
    path = settings.keys_dir / "session_secret"
    if path.exists():
        return path.read_text("utf-8").strip()
    secret = secrets.token_urlsafe(48)
    path.write_text(secret, encoding="utf-8")
    return secret


def _setup_logging() -> None:
    settings.ensure_dirs()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(settings.logs_dir / "backend.log"),
        ],
    )


def _patch_schema(engine) -> None:
    """Idempotently apply additive column changes that ``create_all`` cannot
    perform on existing tables. SQLite supports ``ALTER TABLE ADD COLUMN``;
    other dialects do too. Safe to run on every boot.
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "child_profiles" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("child_profiles")}
    if "custom_watch_phrases" not in cols:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE child_profiles ADD COLUMN custom_watch_phrases TEXT DEFAULT '[]'"
            ))
        log.info("schema patch: added child_profiles.custom_watch_phrases")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    settings.ensure_dirs()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _patch_schema(engine)
    if settings.mdns_enabled:
        try:
            mdns_advertiser.start()
        except Exception as e:  # pragma: no cover
            log.warning("mDNS start failed: %s", e)
    cleanup_task = None
    if settings.retention_cleanup_enabled:
        cleanup_task = asyncio.create_task(cleanup_worker.loop())
    log.info("GuardianNode backend %s listening on %s:%s", __version__, settings.bind_host, settings.bind_port)
    try:
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
        try:
            mdns_advertiser.stop()
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="GuardianNode",
        version=__version__,
        description="Local-first parental safety monitor",
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=_ensure_session_secret(),
        same_site="strict",
        https_only=False,  # local LAN — TLS optional
        max_age=60 * 60 * 24 * 7,
    )

    if settings.cors_allow_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.cors_allow_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_api.router, prefix="/api")
    app.include_router(auth_api.router, prefix="/api")
    app.include_router(setup_api.router, prefix="/api")
    app.include_router(devices_api.router, prefix="/api")
    app.include_router(profiles_api.router, prefix="/api")
    app.include_router(policies_api.router, prefix="/api")
    app.include_router(events_api.router, prefix="/api")
    app.include_router(risks_api.router, prefix="/api")
    app.include_router(alerts_api.router, prefix="/api")
    app.include_router(models_api.router, prefix="/api")
    app.include_router(dashboard_api.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")
    app.include_router(storage_api.router, prefix="/api")
    app.include_router(audit_api.router, prefix="/api")
    app.include_router(child_requests_api.router, prefix="/api")

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists() and any(static_dir.iterdir()):
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str, request: Request):
            # API routes already matched above; anything else returns the SPA index.
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            # Root-level static files (favicon.ico, icons, logos) are served
            # directly; everything else falls through to the SPA index.
            if full_path:
                candidate = (static_dir / full_path).resolve()
                if candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
                    return FileResponse(candidate)
            index = static_dir / "index.html"
            if not index.exists():
                return JSONResponse({"detail": "dashboard not built"}, status_code=404)
            return FileResponse(index)
    else:
        @app.get("/")
        def root_no_dashboard():
            return {
                "service": "guardiannode-backend",
                "version": __version__,
                "note": "Dashboard not built. Run `npm run build` in dashboard/ and copy dist/ to backend/app/static/, or run the dashboard dev server separately.",
                "api_docs": "/docs" if settings.dev_mode else None,
            }

    return app


app = create_app()


def cli() -> None:  # pragma: no cover
    """Console entry point used by the PyInstaller bundle and Linux installer."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.bind_host,
        port=settings.bind_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    cli()
