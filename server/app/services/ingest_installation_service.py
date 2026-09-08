import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github_installation import GitHubInstallation
from app.models.repository import Repository
from app.models.tenant_user import TenantUser
from app.models.user import User
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

    # Match installation to tenant by GitHub account ID — the user who installs
    # the App must already have signed in (so we have their github_account_id),
    # and the tenant is the one where they hold an owner membership. We pick
    # the owned tenant rather than any membership so a user being a member of
    # someone else's tenant doesn't cause the install to land there.
    github_account_id = installation_data["account"]["id"]
    user_result = await session.execute(select(User).where(User.github_account_id == github_account_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        logger.warning(
            "installation:created received for unknown github account %s (id=%s) — skipping",
            installation_data["account"]["login"],
            github_account_id,
        )
        return

    membership_result = await session.execute(
        select(TenantUser.tenant_id)
        .where(TenantUser.user_id == user.id, TenantUser.role == "owner")
        .limit(1)
    )
    tenant_id = membership_result.scalar_one_or_none()

    if tenant_id is None:
        logger.warning(
            "installation:created for github account %s but user %s owns no tenant — skipping",
            installation_data["account"]["login"],
            user.id,
        )
        return

    # Upsert installation
    stmt = (
        insert(GitHubInstallation)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            installation_id=installation_data["id"],
            account_login=installation_data["account"]["login"],
            account_type=installation_data["account"]["type"].lower(),
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "installation_id"],
            set_={
                "account_login": installation_data["account"]["login"],
                "account_type": installation_data["account"]["type"].lower(),
            },
        )
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

    # Discover environments for each repo
    github = GitHubClient()
    try:
        repo_result = await session.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.installation_id == installation.id,
            )
        )
        db_repos = repo_result.scalars().all()
        for repo in db_repos:
            owner, name = repo.full_name.split("/", 1)
            envs = await github.list_environments(owner, name, installation.installation_id)
            await discover_environments(tenant_id, repo, envs, session)
    finally:
        await github.close()


async def sync_repos(
    tenant_id: uuid.UUID,
    installation: GitHubInstallation,
    repos_data: list[dict],
    session: AsyncSession,
) -> None:
    for repo_data in repos_data:
        stmt = (
            insert(Repository)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                installation_id=installation.id,
                github_id=repo_data["id"],
                full_name=repo_data["full_name"],
                default_branch=repo_data.get("default_branch", "main"),
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "github_id"],
                set_={
                    "full_name": repo_data["full_name"],
                    "default_branch": repo_data.get("default_branch", "main"),
                },
            )
        )
        await session.execute(stmt)
    await session.flush()
