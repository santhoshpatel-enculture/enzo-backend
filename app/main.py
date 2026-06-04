"""Enzo Backend — FastAPI application entry point.

Security headers applied:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: camera=(), microphone=(), geolocation=()
- Content-Security-Policy: default-src 'self'
- Strict CORS with explicit allowed origins (no wildcard)

TODO(security): Add rate limiting middleware (slowapi) for production.
TODO(security): Add CSRF protection if switching to cookie-based auth.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import connect_db, close_db, get_db, is_db_connected

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("enzo.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect DB + seed. Shutdown: close DB."""
    await connect_db()
    from app.services.prompt_files import ensure_prompt_files
    from app.services.platform_config import seed_platform_config_from_files

    ensure_prompt_files()
    await seed_platform_config_from_files()
    from app.services.platform_config import seed_tenant_configs
    from app.services.admin_rbac import bootstrap_admin_roles

    await seed_tenant_configs()
    await bootstrap_admin_roles(get_db())
    logger.info("Enzo backend started (env=%s)", settings.app_env)
    yield
    await close_db()


app = FastAPI(
    title="Enzo — Enculture AI Assistant",
    description="Premium AI assistant backend for the Enculture platform.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — strict origin allowlist (no wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Request-Id",
        "X-Admin-Tenant-Id",
    ],
    expose_headers=["X-Conversation-Id"],
)


# Ensure MongoDB is connected (serverless cold starts may skip lifespan timing)
@app.middleware("http")
async def ensure_database(request: Request, call_next):
    if not is_db_connected():
        await connect_db()
    return await call_next(request)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


# Register routers
from app.routers import (
    auth,
    auth_sso,
    profile,
    tasks,
    chat,
    dashboard,
    settings as settings_router,
    admin,
    org,
    programs,
    platform,
)

app.include_router(auth.router, prefix="/api")
app.include_router(auth_sso.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(org.router, prefix="/api")
app.include_router(programs.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(platform.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "enzo-backend"}
