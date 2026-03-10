import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.github_installation import GitHubInstallation
from app.db.models.repository import Repository
from app.services.environment_service import discover_environments
from app.services.github_client import GitHubClient
from app.services.webhook_service import register_handler

logger = logging.getLogger(__name__)


@register_handler("installation")
async def handle_installation_event(payload: dict, session: AsyncSession) -> None:
    action = payload.get("action")
    if action == "created":
        await _handle_created(payload, session)
    elif action == "deleted":
        logger.info("installation deleted, installation_id=%s", payload["installation"]["id"])


async def _handle_created(payload: dict, session: AsyncSession) -> None:
    installation_data = payload["installation"]
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    # Upsert installation
    stmt = insert(GitHubInstallation).values(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        installation_id=installation_data["id"],
        account_login=installation_data["account"]["login"],
        account_type=installation_data["account"]["type"].lower(),
    ).on_conflict_do_update(
        index_elements=["tenant_id", "installation_id"],
        set_={
            "account_login": installation_data["account"]["login"],
            "account_type": installation_data["account"]["type"].lower(),
        },
    )
    await session.execute(stmt)
    await session.flush()

    # Get the installation record
    result = await session.execute(
        select(GitHubInstallation).where(
            GitHubInstallation.tenant_id == tenant_id,
            GitHubInstallation.installation_id == installation_data["id"],
        )
    )
    installation = result.scalar_one()

    # Sync repos from payload (repos included in installation event)
    repos = payload.get("repositories", [])
    await sync_repos(tenant_id, installation, repos, session)


async def sync_repos(
    tenant_id: uuid.UUID,
    installation: GitHubInstallation,
    repos_data: list[dict],
    session: AsyncSession,
) -> None:
    for repo_data in repos_data:
        stmt = insert(Repository).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            installation_id=installation.id,
            github_id=repo_data["id"],
            full_name=repo_data["full_name"],
            default_branch=repo_data.get("default_branch", "main"),
        ).on_conflict_do_update(
            index_elements=["tenant_id", "github_id"],
            set_={
                "full_name": repo_data["full_name"],
                "default_branch": repo_data.get("default_branch", "main"),
            },
        )
        await session.execute(stmt)
    await session.flush()
