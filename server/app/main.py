from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import dispose_db, init_db
from app.logging import configure_logging
from app.routes import deployments, health, metrics, pull_requests, repos, webhooks

# Import services to register webhook handlers
import app.services.installation_service  # noqa: F401
import app.services.deployment_service  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings)
    await init_db()
    yield
    await dispose_db()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(repos.router, prefix="/api")
    app.include_router(deployments.router, prefix="/api")
    app.include_router(pull_requests.router, prefix="/api")
    app.include_router(metrics.router, prefix="/api")
    return app


app = create_app()
