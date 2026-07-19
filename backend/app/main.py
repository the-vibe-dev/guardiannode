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
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app import settings as settings_mod
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
from app.api import demo as demo_api
from app.api import (
    devices as devices_api,
)
from app.api import (
    events as events_api,
)
from app.api import guardian_review as guardian_review_api
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
from app.db.session import get_engine
from app.services import mdns_advertiser
from app.services.device_bootstrap_token import ensure_device_bootstrap_token
from app.services.setup_token import ensure_setup_token
from app.settings import settings
from app.workers import (
    backup_worker,
    cleanup_worker,
    guardian_review_worker,
    notification_worker,
    offline_monitor,
)

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


def _host_without_port(host_header: str) -> str:
    host_header = host_header.strip()
    if host_header.startswith("["):
        end = host_header.find("]")
        if end != -1:
            return host_header[1:end]
    if host_header.count(":") == 1:
        host, port = host_header.rsplit(":", 1)
        if port.isdigit():
            return host
    return host_header


class HostHeaderMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: list[str]):
        super().__init__(app)
        self.allowed_hosts = {
            host[1:-1] if host.startswith("[") and host.endswith("]") else host
            for host in allowed_hosts
        }

    async def dispatch(self, request: Request, call_next):
        host = _host_without_port(request.headers.get("host", ""))
        if host not in self.allowed_hosts:
            return PlainTextResponse("Invalid host header", status_code=400)
        return await call_next(request)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    settings.ensure_dirs()
    engine = get_engine()
    from app.db.migrations import upgrade_schema

    migration_result = upgrade_schema(engine)
    log.info("database schema ready: %s", migration_result)
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
        ensure_setup_token()
        log.warning(
            "first-run setup token required; read it from %s",
            settings.keys_dir / "setup_token.json",
        )
    if not paired_device_exists:
        ensure_device_bootstrap_token()
        log.warning(
            "local device bootstrap token available at %s",
            settings.keys_dir / "device_bootstrap_token.json",
        )
    if settings.mdns_enabled:
        try:
            mdns_advertiser.start()
        except Exception as e:  # pragma: no cover
            log.warning("mDNS start failed: %s", e)
    from app.services import worker_supervisor

    background_tasks = []
    # Single-consumer screenshot classification worker (stores on arrival,
    # classifies one frame at a time so the vision model isn't hit concurrently).
    from app.services import screenshot_async
    background_tasks.append(
        asyncio.create_task(worker_supervisor.supervise("screenshot", screenshot_async.loop))
    )
    if settings.retention_cleanup_enabled:
        background_tasks.append(
            asyncio.create_task(worker_supervisor.supervise("retention", cleanup_worker.loop))
        )
    if settings.device_offline_alert_enabled:
        background_tasks.append(
            asyncio.create_task(worker_supervisor.supervise("offline", offline_monitor.loop))
        )
    if settings.notification_worker_enabled:
        background_tasks.append(
            asyncio.create_task(
                worker_supervisor.supervise("notifications", notification_worker.loop)
            )
        )
    if settings.database_backup_enabled:
        background_tasks.append(
            asyncio.create_task(worker_supervisor.supervise("backup", backup_worker.loop))
        )
    if settings.guardian_review_enabled:
        background_tasks.append(
            asyncio.create_task(
                worker_supervisor.supervise("guardian_review", guardian_review_worker.loop)
            )
        )
    log.info("GuardianNode backend %s listening on %s:%s", __version__, settings.bind_host, settings.bind_port)
    if settings.binds_beyond_loopback():
        log.warning(
            "GuardianNode backend is listening beyond loopback; keep it on a trusted "
            "LAN/VPN/TLS path and do not expose it directly to the public internet."
        )
    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        try:
            mdns_advertiser.stop()
        except Exception:
            pass


def create_app() -> FastAPI:
    global settings
    settings = settings_mod.settings
    # Settings are replaceable in tests and maintenance commands. Keep modules
    # that cache the imported singleton aligned with the effective app config.
    health_api.settings = settings
    models_api.settings = settings
    from app.services import screenshot_ingest

    screenshot_ingest.settings = settings
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
        app.add_middleware(HostHeaderMiddleware, allowed_hosts=allowed_hosts)

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
    app.include_router(guardian_review_api.router, prefix="/api")
    app.include_router(demo_api.router, prefix="/api")
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
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="guardiannode-backend")
    subparsers = parser.add_subparsers(dest="command")
    preflight_parser = subparsers.add_parser("preflight", help="validate active pipeline dependencies")
    preflight_parser.add_argument("--pull-models", action="store_true")
    preflight_parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    if args.command == "preflight":
        from app.preflight import run

        code, body = asyncio.run(run(pull_models=args.pull_models))
        if args.as_json:
            print(json.dumps(body, sort_keys=True, default=str))
        else:
            for name, check in body["checks"].items():
                print(f"{name}: {'ok' if check.get('ok') else check.get('error_code', 'failed')}")
        raise SystemExit(code)

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.bind_host,
        port=settings.bind_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    cli()
