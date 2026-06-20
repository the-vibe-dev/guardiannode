"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api import (
    alerts as alerts_api,
)
from app.api import (
    audit as audit_api,
)
from app.api import (
    auth as auth_api,
)
from app.api import (
    child_requests as child_requests_api,
)
from app.api import (
    dashboard as dashboard_api,
)
from app.api import (
    devices as devices_api,
)
from app.api import (
    events as events_api,
)
from app.api import (
    health as health_api,
)
from app.api import (
    models as models_api,
)
from app.api import (
    policies as policies_api,
)
from app.api import (
    profiles as profiles_api,
)
from app.api import (
    risks as risks_api,
)
from app.api import (
    settings as settings_api,
)
from app.api import (
    setup as setup_api,
)
from app.api import (
    storage as storage_api,
)
from app.db.models import Base
from app.db.session import get_engine
from app.services import mdns_advertiser
from app.services.device_bootstrap_token import ensure_device_bootstrap_token
from app.services.setup_token import ensure_setup_token
from app.settings import settings
from app.workers import cleanup_worker, notification_worker, offline_monitor

log = logging.getLogger("guardiannode")

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_CSRF_EXEMPT_API_PATHS = {
    "/api/devices/pair/complete",
    "/api/devices/bootstrap-local",
    "/api/devices/heartbeat",
    "/api/events",
    "/api/events/screenshot",
    "/api/child-requests",
}


class BrowserSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _MUTATING_METHODS:
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlparse

                parsed = urlparse(origin)
                host = request.headers.get("host", "")
                if parsed.netloc != host:
                    return JSONResponse({"detail": "invalid origin"}, status_code=403)
            if self._requires_csrf(request):
                expected = str(request.session.get("csrf_token") or "")
                supplied = request.headers.get("x-csrf-token", "")
                if not expected or not hmac.compare_digest(expected, supplied):
                    return JSONResponse({"detail": "invalid csrf token"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'",
        )
        return response

    @staticmethod
    def _requires_csrf(request: Request) -> bool:
        if not request.url.path.startswith("/api/"):
            return False
        if request.url.path in _CSRF_EXEMPT_API_PATHS:
            return False
        if request.headers.get("authorization", "").lower().startswith("bearer "):
            return False
        return bool(request.session.get("user_id"))


def _ensure_session_secret() -> str:
    if settings.session_secret:
        return settings.session_secret
    settings.ensure_dirs()
    path = settings.keys_dir / "session_secret"
    if path.exists():
        return path.read_text("utf-8").strip()
    secret = secrets.token_urlsafe(48)
    path.write_text(secret, encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
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
    tables = insp.get_table_names()
    if "child_profiles" in tables:
        cols = {c["name"] for c in insp.get_columns("child_profiles")}
        if "custom_watch_phrases" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE child_profiles ADD COLUMN custom_watch_phrases TEXT DEFAULT '[]'"
                ))
            log.info("schema patch: added child_profiles.custom_watch_phrases")
        if "alert_policy" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE child_profiles ADD COLUMN alert_policy TEXT DEFAULT '{}'"
                ))
            log.info("schema patch: added child_profiles.alert_policy")
    if "alerts" in tables:
        cols = {c["name"] for c in insp.get_columns("alerts")}
        patches = {
            "dedup_key": "ALTER TABLE alerts ADD COLUMN dedup_key VARCHAR(64)",
            "repeat_count": "ALTER TABLE alerts ADD COLUMN repeat_count INTEGER DEFAULT 1",
            "last_seen_at": "ALTER TABLE alerts ADD COLUMN last_seen_at DATETIME",
        }
        for col, ddl in patches.items():
            if col not in cols:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                log.info("schema patch: added alerts.%s", col)
    if "devices" in tables:
        cols = {c["name"] for c in insp.get_columns("devices")}
        if "profile_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE devices ADD COLUMN profile_id VARCHAR(64)"))
            log.info("schema patch: added devices.profile_id")
    if "users" in tables:
        cols = {c["name"] for c in insp.get_columns("users")}
        if "session_revoked_at" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN session_revoked_at DATETIME"))
            log.info("schema patch: added users.session_revoked_at")
        existing_indexes = {ix["name"] for ix in insp.get_indexes("users")}
        if "ux_users_single_admin" not in existing_indexes:
            with engine.begin() as conn:
                if engine.dialect.name == "sqlite":
                    conn.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_admin "
                        "ON users(role) WHERE role = 'admin'"
                    ))
                elif engine.dialect.name == "postgresql":
                    conn.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_admin "
                        "ON users(role) WHERE role = 'admin'"
                    ))
            log.info("schema patch: ensured users single-admin index")
    if "risk_results" in tables:
        cols = {c["name"] for c in insp.get_columns("risk_results")}
        if "classifier_status" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE risk_results ADD COLUMN classifier_status VARCHAR(48) DEFAULT 'ok'"
                ))
            log.info("schema patch: added risk_results.classifier_status")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    settings.ensure_dirs()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _patch_schema(engine)
    storage_api._cleanup_abandoned_exports()
    from app.db.models import Device, User
    from app.db.session import get_sessionmaker
    s = get_sessionmaker()()
    try:
        admin_exists = s.query(User).filter(User.role == "admin").first() is not None
        paired_device_exists = s.query(Device).filter(Device.paired.is_(True)).first() is not None
    finally:
        s.close()
    if not admin_exists:
        token = ensure_setup_token()
        log.warning(
            "first-run setup token required; read it from %s (current token starts with %s...)",
            settings.keys_dir / "setup_token.json",
            token[:6],
        )
    if not paired_device_exists:
        token = ensure_device_bootstrap_token()
        log.warning(
            "local device bootstrap token available at %s (current token starts with %s...)",
            settings.keys_dir / "device_bootstrap_token.json",
            token[:6],
        )
    if settings.mdns_enabled:
        try:
            mdns_advertiser.start()
        except Exception as e:  # pragma: no cover
            log.warning("mDNS start failed: %s", e)
    background_tasks = []
    # Single-consumer screenshot classification worker (stores on arrival,
    # classifies one frame at a time so the vision model isn't hit concurrently).
    from app.services import screenshot_async
    background_tasks.append(asyncio.create_task(screenshot_async.loop()))
    if settings.retention_cleanup_enabled:
        background_tasks.append(asyncio.create_task(cleanup_worker.loop()))
    if settings.device_offline_alert_enabled:
        background_tasks.append(asyncio.create_task(offline_monitor.loop()))
    if settings.notification_worker_enabled:
        background_tasks.append(asyncio.create_task(notification_worker.loop()))
    log.info("GuardianNode backend %s listening on %s:%s", __version__, settings.bind_host, settings.bind_port)
    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
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
        docs_url="/docs" if settings.dev_mode else None,
        redoc_url="/redoc" if settings.dev_mode else None,
        openapi_url="/openapi.json" if settings.dev_mode else None,
    )

    app.add_middleware(BrowserSecurityMiddleware)

    allowed_hosts = settings.effective_allowed_hosts()
    if allowed_hosts and allowed_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    app.add_middleware(
        SessionMiddleware,
        secret_key=_ensure_session_secret(),
        same_site="strict",
        https_only=settings.https_only_cookies,
        max_age=settings.session_absolute_timeout_seconds,
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
