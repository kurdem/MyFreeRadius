"""FreeRADIUS Manager - FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    active_directory,
    auth,
    clients,
    configuration,
    health,
    logs,
    mfa,
    radius,
)
from app.config import get_settings
from app.logging_conf import configure_logging
from app.security.crypto import SecretCryptoError
from app.services.seed import bootstrap_admin, init_db

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Fail loud and early on secret-key misconfiguration (common setup mistake).
    try:
        from app.security.crypto import validate_key

        validate_key()
    except Exception as exc:  # noqa: BLE001 - surface the exact reason at boot
        logger.error("startup", extra={"event": "fernet_key_invalid", "result": str(exc)})
    init_db()
    bootstrap_admin()
    logger.info("startup", extra={"event": "app_started", "result": __version__})
    yield


settings = get_settings()

app = FastAPI(
    title="FreeRADIUS Manager API",
    version=__version__,
    description="Management API for a FreeRADIUS appliance (Horizon View / AD).",
    lifespan=lifespan,
)

# CORS - only the configured frontend origin, credentials allowed for cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(SecretCryptoError)
async def secret_crypto_error_handler(request: Request, exc: SecretCryptoError):
    # Configuration error (e.g. invalid FERNET_KEY). The message is guidance, not
    # sensitive data, so return it verbatim in every environment.
    logger.error("crypto_config_error", extra={"event": "error", "result": str(exc)})
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak internals in production (spec section 26).
    logger.exception("unhandled_error", extra={"event": "error"})
    detail = "Internal server error" if settings.is_production else repr(exc)
    return JSONResponse(status_code=500, content={"detail": detail})


API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(clients.router, prefix=API)
app.include_router(clients.group_router, prefix=API)
app.include_router(configuration.router, prefix=API)
app.include_router(active_directory.router, prefix=API)
app.include_router(mfa.router, prefix=API)
app.include_router(radius.router, prefix=API)
app.include_router(logs.router, prefix=API)
app.include_router(health.router, prefix=API)
