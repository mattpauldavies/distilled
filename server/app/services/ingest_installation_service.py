import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
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
        await _handle_deleted(payload, session)


@register_handler("installation_repositories")
async def handle_installation_repositories_event(payload: dict, session: AsyncSession) -> None:
    action = payload.get("action")
    installation = await _get_installation(payload["installation"]["id"], session)
    if installation is None:
        logger.warning(
            "installation_repositories:%s received for unknown installation_id=%s — skipping",
            action,
            payload["installation"]["id"],
        )
        return

    if action == "added":
        await _handle_repositories_added(payload, installation, session)
    elif action == "removed":
        await _handle_repositories_removed(payload, installation, session)


async def _get_installation(installation_id: int, session: AsyncSession) -> GitHubInstallation | None:
    result = await session.execute(
        select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
    )
    return result.scalar_one_or_none()


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

    # Upsert installation; clearing removed_at resurrects a soft-deleted install
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
                "removed_at": None,
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

    # Discover environments for every repo of the installation
    repo_result = await session.execute(
        select(Repository).where(
            Repository.tenant_id == tenant_id,
            Repository.installation_id == installation.id,
        )
    )
    await _discover_repo_environments(tenant_id, installation, repo_result.scalars().all(), session)


async def _handle_deleted(payload: dict, session: AsyncSession) -> None:
    installation = await _get_installation(payload["installation"]["id"], session)
    if installation is None:
        logger.warning(
            "installation:deleted received for unknown installation_id=%s — skipping",
            payload["installation"]["id"],
        )
        return

    now = datetime.now(UTC)
    await session.execute(
        update(Repository)
        .where(
            Repository.tenant_id == installation.tenant_id,
            Repository.installation_id == installation.id,
        )
        .values(removed_at=now)
    )
    await session.execute(
        update(GitHubInstallation).where(GitHubInstallation.id == installation.id).values(removed_at=now)
    )
    await session.flush()
    logger.info(
        "installation deleted, soft-deleted installation_id=%s and its repos",
        installation.installation_id,
    )


async def _handle_repositories_added(
    payload: dict, installation: GitHubInstallation, session: AsyncSession
) -> None:
    repos_data = payload.get("repositories_added", [])
    await sync_repos(installation.tenant_id, installation, repos_data, session)

    added_github_ids = [repo_data["id"] for repo_data in repos_data]
    repo_result = await session.execute(
        select(Repository).where(
            Repository.tenant_id == installation.tenant_id,
            Repository.installation_id == installation.id,
            Repository.github_id.in_(added_github_ids),
        )
    )
    await _discover_repo_environments(
        installation.tenant_id, installation, repo_result.scalars().all(), session
    )


async def _handle_repositories_removed(
    payload: dict, installation: GitHubInstallation, session: AsyncSession
) -> None:
    removed_github_ids = [repo_data["id"] for repo_data in payload.get("repositories_removed", [])]
    if not removed_github_ids:
        return

    await session.execute(
        update(Repository)
        .where(
            Repository.tenant_id == installation.tenant_id,
            Repository.installation_id == installation.id,
            Repository.github_id.in_(removed_github_ids),
        )
        .values(removed_at=datetime.now(UTC))
    )
    await session.flush()


async def _discover_repo_environments(
    tenant_id: uuid.UUID,
    installation: GitHubInstallation,
    repos: Sequence[Repository],
    session: AsyncSession,
) -> None:
    github = GitHubClient()
    try:
        for repo in repos:
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
        # installation_repositories payloads omit default_branch — leave an
        # existing row's value alone rather than clobbering it back to "main".
        conflict_set: dict = {
            "full_name": repo_data["full_name"],
            "removed_at": None,
        }
        if "default_branch" in repo_data:
            conflict_set["default_branch"] = repo_data["default_branch"]

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
                set_=conflict_set,
            )
        )
        await session.execute(stmt)
    await session.flush()
