import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github_installation import GitHubInstallation
from app.models.repository import Repository
from app.models.tenant_installation import TenantInstallation
from app.services import installation_link_service
from app.services.installation_link_service import (  # noqa: F401 — sync_repos re-exported for tests
    discover_repo_environments,
    get_installation_by_github_id,
    sync_repos,
)
from app.services.webhook_service import SKIPPED, register_handler

logger = logging.getLogger(__name__)


@register_handler("installation")
async def handle_installation_event(payload: dict, session: AsyncSession) -> str | None:
    action = payload.get("action")
    if action == "created":
        return await _handle_created(payload, session)
    if action == "deleted":
        return await _handle_deleted(payload, session)
    return SKIPPED


@register_handler("installation_repositories")
async def handle_installation_repositories_event(payload: dict, session: AsyncSession) -> str | None:
    action = payload.get("action")
    installation_id = payload["installation"]["id"]

    # A configure-only visit may fire this event without a setup redirect —
    # the sender can still claim an open intent here.
    await installation_link_service.claim_by_sender(
        payload.get("sender", {}).get("id"), installation_id, session
    )

    installation = await get_installation_by_github_id(installation_id, session)
    if installation is None:
        logger.warning(
            "installation_repositories:%s received for unknown installation_id=%s — skipping",
            action,
            installation_id,
        )
        return SKIPPED

    if action == "added":
        await _handle_repositories_added(payload, installation, session)
    elif action == "removed":
        await _handle_repositories_removed(payload, installation, session)
    else:
        return SKIPPED
    return None


async def _linked_tenant_ids(
    installation: GitHubInstallation, session: AsyncSession
) -> list[uuid.UUID]:
    result = await session.execute(
        select(TenantInstallation.tenant_id).where(
            TenantInstallation.github_installation_id == installation.id
        )
    )
    return list(result.scalars().all())


async def _handle_created(payload: dict, session: AsyncSession) -> str | None:
    installation_data = payload["installation"]
    installation_id = installation_data["id"]

    # Upsert the global installation record; re-install resurrects it.
    installation = await get_installation_by_github_id(installation_id, session)
    if installation is None:
        installation = GitHubInstallation(
            id=uuid.uuid4(),
            installation_id=installation_id,
            account_login=installation_data["account"]["login"],
            account_type=installation_data["account"]["type"].lower(),
        )
        session.add(installation)
        await session.flush()
    else:
        installation.account_login = installation_data["account"]["login"]
        installation.account_type = installation_data["account"]["type"].lower()
        installation.removed_at = None

    # The sender is the person who completed the install on GitHub; if they
    # hold an open intent, this binds the installation to their workspace
    # (including the full repo sync).
    await installation_link_service.claim_by_sender(
        payload.get("sender", {}).get("id"), installation_id, session
    )

    tenant_ids = await _linked_tenant_ids(installation, session)
    if not tenant_ids:
        logger.warning(
            "installation:created for account %s (installation_id=%s) has no linked "
            "workspace and no open intent for sender — held unclaimed",
            installation_data["account"]["login"],
            installation_id,
        )
        return SKIPPED

    # Resync payload repos into every linked workspace. Webhook syncs respect
    # sticky removals — only an explicit user action resurrects a removed repo.
    repos = payload.get("repositories", [])
    added_github_ids = [repo_data["id"] for repo_data in repos]
    for tenant_id in tenant_ids:
        await sync_repos(tenant_id, installation, repos, session, respect_removed=True)
        repo_result = await session.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.installation_id == installation.id,
                Repository.github_id.in_(added_github_ids),
                Repository.removed_at.is_(None),
            )
        )
        await discover_repo_environments(
            tenant_id, installation, repo_result.scalars().all(), session
        )
    return None


async def _handle_deleted(payload: dict, session: AsyncSession) -> str | None:
    installation = await get_installation_by_github_id(payload["installation"]["id"], session)
    if installation is None:
        logger.warning(
            "installation:deleted received for unknown installation_id=%s — skipping",
            payload["installation"]["id"],
        )
        return SKIPPED

    now = datetime.now(UTC)
    # One statement spans every linked workspace's rows for this installation.
    await session.execute(
        update(Repository)
        .where(Repository.installation_id == installation.id)
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
    return None


async def _handle_repositories_added(
    payload: dict, installation: GitHubInstallation, session: AsyncSession
) -> None:
    repos_data = payload.get("repositories_added", [])
    added_github_ids = [repo_data["id"] for repo_data in repos_data]

    for tenant_id in await _linked_tenant_ids(installation, session):
        await sync_repos(tenant_id, installation, repos_data, session, respect_removed=True)
        repo_result = await session.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.installation_id == installation.id,
                Repository.github_id.in_(added_github_ids),
                Repository.removed_at.is_(None),
            )
        )
        await discover_repo_environments(
            tenant_id, installation, repo_result.scalars().all(), session
        )


async def _handle_repositories_removed(
    payload: dict, installation: GitHubInstallation, session: AsyncSession
) -> None:
    removed_github_ids = [repo_data["id"] for repo_data in payload.get("repositories_removed", [])]
    if not removed_github_ids:
        return

    # One statement spans every linked workspace's rows for this installation.
    await session.execute(
        update(Repository)
        .where(
            Repository.installation_id == installation.id,
            Repository.github_id.in_(removed_github_ids),
        )
        .values(removed_at=datetime.now(UTC))
    )
    await session.flush()
