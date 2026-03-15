import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import dispose_db, init_db
from app.logging import configure_logging
from app.routes import deployments, environments, health, metrics, pull_requests, repos, webhooks

logger = logging.getLogger(__name__)

# Import services to register webhook handlers
import app.services.installation_service
import app.services.deployment_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings)
    await init_db()
    yield
    await dispose_db()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception for %s %s", request.method, request.url)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(repos.router, prefix="/api")
    app.include_router(environments.router, prefix="/api")
    app.include_router(deployments.router, prefix="/api")
    app.include_router(pull_requests.router, prefix="/api")
    app.include_router(metrics.router, prefix="/api")
    return app


app = create_app()
