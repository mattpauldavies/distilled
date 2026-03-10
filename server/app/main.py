from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import health, items


def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(items.router, prefix="/api")
    return app


app = create_app()
