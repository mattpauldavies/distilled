import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth import require_auth
from app.config import settings
from app.db import dispose_db, init_db
from app.logging import configure_logging
from app.routes import deployments, environments, health, metrics, pull_requests, repos, webhooks

logger = logging.getLogger(__name__)

# Import services to register webhook handlers
import app.services.deployment_service
import app.services.installation_service

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings)
    await init_db()
    yield
    await dispose_db()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception for %s %s", request.method, request.url)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    app.include_router(health.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(repos.router, prefix="/api", dependencies=[Depends(require_auth)])
    app.include_router(environments.router, prefix="/api", dependencies=[Depends(require_auth)])
    app.include_router(deployments.router, prefix="/api", dependencies=[Depends(require_auth)])
    app.include_router(pull_requests.router, prefix="/api", dependencies=[Depends(require_auth)])
    app.include_router(metrics.router, prefix="/api")  # no router-level auth — per-route in metrics.py
    return app


app: FastAPI = create_app()  # type: ignore[no-redef]
