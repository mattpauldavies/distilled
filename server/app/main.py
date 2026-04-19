import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth import require_auth
from app.config import settings
from app.db import dispose_db, init_db
from app.logging import configure_logging
from app.rate_limit import limiter
from app.routes import deployments, environments, health, metrics, pull_requests, repos, webhooks

logger = logging.getLogger(__name__)

# Import services to register webhook handlers
import app.services.deployment_service
import app.services.installation_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings)
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
        )
    await init_db()
    yield
    await dispose_db()


def create_app() -> FastAPI:
    is_prod = settings.environment == "production"
    app = FastAPI(
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception for %s %s", request.method, request.url)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    docs_paths = {"/docs", "/redoc", "/openapi.json"}

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if is_prod:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path not in docs_paths:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(repos.router, dependencies=[Depends(require_auth)])
    app.include_router(environments.router, dependencies=[Depends(require_auth)])
    app.include_router(deployments.router, dependencies=[Depends(require_auth)])
    app.include_router(pull_requests.router, dependencies=[Depends(require_auth)])
    app.include_router(metrics.router)  # no router-level auth — per-route in metrics.py
    return app


app: FastAPI = create_app()  # type: ignore[no-redef]
