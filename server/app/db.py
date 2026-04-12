import ssl
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

connect_args: dict = {}
if settings.environment == "production":
    ssl_context = ssl.create_default_context()
    connect_args["ssl"] = ssl_context

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
    connect_args=connect_args,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Called on app startup — verifies connectivity."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def dispose_db() -> None:
    await engine.dispose()
