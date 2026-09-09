import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environment import Environment
from app.models.repository import Repository

logger = logging.getLogger(__name__)

# Substring match, not exact: environments are commonly namespaced or suffixed
# ("distilled / production", "prod-eu"). "production" is covered by "prod".
PRODUCTION_PATTERN = re.compile(r"prod|live", re.IGNORECASE)


def detect_production(name: str) -> bool:
    return bool(PRODUCTION_PATTERN.search(name))


async def get_production_environments(
    tenant_id: uuid.UUID,
    repo_id: uuid.UUID,
    session: AsyncSession,
) -> list[str]:
    result = await session.execute(
        select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.repo_id == repo_id,
            Environment.is_production.is_(True),
        )
    )
    envs = result.scalars().all()
    return [env.name for env in envs]


async def discover_environments(
    tenant_id: uuid.UUID,
    repo: Repository,
    environments_data: list[dict],
    session: AsyncSession,
) -> None:
    for env_data in environments_data:
        name = env_data["name"]
        is_prod = detect_production(name)

        stmt = (
            insert(Environment)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                repo_id=repo.id,
                name=name,
                is_production=is_prod,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "repo_id", "name"],
            )
        )
        await session.execute(stmt)
