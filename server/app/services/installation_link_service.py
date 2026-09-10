"""User-initiated binding of GitHub App installations to workspaces.

Installations are global records — one GitHub account holds at most one
installation of the App — shared across workspaces via tenant_installations.
This module owns the intent/claim/link lifecycle and per-workspace repository
curation. Webhook-driven repo lifecycle lives in ingest_installation_service,
which shares the sync helpers defined here.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.github_installation import GitHubInstallation
from app.models.installation_intent import InstallationIntent
from app.models.repository import Repository
from app.models.tenant import Tenant
from app.models.tenant_installation import TenantInstallation
from app.models.user import User
from app.services.environment_service import discover_environments
from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)


class IntentError(Exception):
    """The installation intent is unknown, expired, consumed, or not the caller's."""


class LinkError(Exception):
    """The workspace/installation/repository relationship the caller assumed doesn't hold."""


@dataclass
class WorkspaceInstallationView:
    installation_id: int
    account_login: str
    account_type: str
    repo_count: int
    removed_at: datetime | None


@dataclass
class AvailableRepo:
    github_id: int
    full_name: str
    default_branch: str | None
    tracked: bool


def _hash_nonce(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_intent(tenant_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession) -> str:
    """Mint the state nonce carried through the GitHub install redirect.

    At most one open intent per user: older open intents are superseded so
    webhook sender matching stays unambiguous.
    """
    await session.execute(
        update(InstallationIntent)
        .where(
            InstallationIntent.user_id == user_id,
            InstallationIntent.consumed_at.is_(None),
        )
        .values(consumed_at=datetime.now(UTC))
    )
    raw = secrets.token_urlsafe(32)
    session.add(
        InstallationIntent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            nonce_hash=_hash_nonce(raw),
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.installation_intent_ttl_minutes),
        )
    )
    await session.commit()
    return raw


async def claim_intent(
    nonce: str, installation_id: int, user_id: uuid.UUID, session: AsyncSession
) -> Tenant:
    """Consume an intent via the GitHub setup callback and bind the installation."""
    result = await session.execute(
        select(InstallationIntent).where(InstallationIntent.nonce_hash == _hash_nonce(nonce))
    )
    intent = result.scalar_one_or_none()
    if intent is None or intent.user_id != user_id:
        raise IntentError("Unknown installation link — reconnect GitHub from your workspace")
    if intent.consumed_at is not None:
        raise IntentError("This installation link has already been used")
    if intent.expires_at < datetime.now(UTC):
        raise IntentError("This installation link has expired — reconnect GitHub from your workspace")

    intent.consumed_at = datetime.now(UTC)
    await bind_installation(intent.tenant_id, installation_id, session)

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == intent.tenant_id))
    return tenant_result.scalar_one()


async def claim_by_sender(
    github_account_id: int | None, installation_id: int, session: AsyncSession
) -> bool:
    """Consume an intent via webhook sender matching (fallback for the callback).

    The webhook's sender is the GitHub user who performed the install/configure
    action; if they hold an open intent, the installation binds to that
    intent's workspace.
    """
    if github_account_id is None:
        return False

    user_result = await session.execute(
        select(User).where(User.github_account_id == github_account_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        return False

    intent_result = await session.execute(
        select(InstallationIntent).where(
            InstallationIntent.user_id == user.id,
            InstallationIntent.consumed_at.is_(None),
            InstallationIntent.expires_at > datetime.now(UTC),
        )
    )
    intent = intent_result.scalar_one_or_none()
    if intent is None:
        return False

    intent.consumed_at = datetime.now(UTC)
    await bind_installation(intent.tenant_id, installation_id, session)
    logger.info(
        "installation %s claimed via sender match for tenant %s",
        installation_id,
        intent.tenant_id,
    )
    return True


async def get_installation_by_github_id(
    installation_id: int, session: AsyncSession
) -> GitHubInstallation | None:
    result = await session.execute(
        select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
    )
    return result.scalar_one_or_none()


async def upsert_installation(
    installation_id: int, account_login: str, account_type: str, session: AsyncSession
) -> GitHubInstallation:
    """Create or refresh the global installation record; resurrects on conflict.

    Race-safe between the webhook and the setup callback: whichever lands
    second updates rather than violating the installation_id constraint.
    """
    stmt = (
        insert(GitHubInstallation)
        .values(
            id=uuid.uuid4(),
            installation_id=installation_id,
            account_login=account_login,
            account_type=account_type.lower(),
        )
        .on_conflict_do_update(
            index_elements=["installation_id"],
            set_={
                "account_login": account_login,
                "account_type": account_type.lower(),
                "removed_at": None,
            },
        )
    )
    await session.execute(stmt)
    await session.flush()
    result = await session.execute(
        select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
    )
    return result.scalar_one()


async def bind_installation(
    tenant_id: uuid.UUID, installation_id: int, session: AsyncSession
) -> GitHubInstallation:
    """Attach an installation to a workspace and sync all its granted repos.

    Idempotent: safe whether the installation row exists yet (webhook races the
    setup callback), whether the link already exists, and on re-binds. An
    explicit bind is a user action, so it resurrects previously removed repos.
    """
    github = GitHubClient()
    try:
        installation = await get_installation_by_github_id(installation_id, session)
        if installation is None:
            data = await github.get_installation(installation_id)
            installation = await upsert_installation(
                installation_id, data["account"]["login"], data["account"]["type"], session
            )
        else:
            installation.removed_at = None

        link_result = await session.execute(
            select(TenantInstallation).where(
                TenantInstallation.tenant_id == tenant_id,
                TenantInstallation.github_installation_id == installation.id,
            )
        )
        if link_result.scalar_one_or_none() is None:
            session.add(
                TenantInstallation(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    github_installation_id=installation.id,
                )
            )
            await session.flush()

        repos_data = await github.list_repos(installation_id)
        await sync_repos(tenant_id, installation, repos_data, session)

        repo_result = await session.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.installation_id == installation.id,
            )
        )
        await discover_repo_environments(
            tenant_id, installation, repo_result.scalars().all(), session, github=github
        )
    finally:
        await github.close()

    await session.commit()
    return installation


async def list_workspace_installations(
    tenant_id: uuid.UUID, session: AsyncSession
) -> list[WorkspaceInstallationView]:
    result = await session.execute(
        select(GitHubInstallation, func.count(Repository.id))
        .join(
            TenantInstallation,
            TenantInstallation.github_installation_id == GitHubInstallation.id,
        )
        .outerjoin(
            Repository,
            (Repository.installation_id == GitHubInstallation.id)
            & (Repository.tenant_id == tenant_id)
            & Repository.removed_at.is_(None),
        )
        .where(TenantInstallation.tenant_id == tenant_id)
        .group_by(GitHubInstallation.id)
        .order_by(GitHubInstallation.account_login)
    )
    return [
        WorkspaceInstallationView(
            installation_id=installation.installation_id,
            account_login=installation.account_login,
            account_type=installation.account_type,
            repo_count=repo_count,
            removed_at=installation.removed_at,
        )
        for installation, repo_count in result.all()
    ]


async def _require_link(
    tenant_id: uuid.UUID, installation_id: int, session: AsyncSession
) -> tuple[GitHubInstallation, TenantInstallation]:
    installation = await get_installation_by_github_id(installation_id, session)
    if installation is None:
        raise LinkError("Installation not found")
    result = await session.execute(
        select(TenantInstallation).where(
            TenantInstallation.tenant_id == tenant_id,
            TenantInstallation.github_installation_id == installation.id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise LinkError("Installation is not connected to this workspace")
    return installation, link


async def unlink_installation(
    tenant_id: uuid.UUID, installation_id: int, session: AsyncSession
) -> None:
    """Detach an installation from one workspace, soft-deleting its repos there."""
    installation, link = await _require_link(tenant_id, installation_id, session)
    await session.execute(
        update(Repository)
        .where(
            Repository.tenant_id == tenant_id,
            Repository.installation_id == installation.id,
            Repository.removed_at.is_(None),
        )
        .values(removed_at=datetime.now(UTC))
    )
    await session.delete(link)
    await session.commit()


async def list_available_repos(
    tenant_id: uuid.UUID, installation_id: int, session: AsyncSession
) -> list[AvailableRepo]:
    """Live grant list from GitHub, annotated with what this workspace tracks."""
    installation, _ = await _require_link(tenant_id, installation_id, session)

    github = GitHubClient()
    try:
        live = await github.list_repos(installation_id)
    finally:
        await github.close()

    tracked_result = await session.execute(
        select(Repository.github_id).where(
            Repository.tenant_id == tenant_id,
            Repository.removed_at.is_(None),
        )
    )
    tracked_ids = set(tracked_result.scalars().all())

    return [
        AvailableRepo(
            github_id=repo["id"],
            full_name=repo["full_name"],
            default_branch=repo.get("default_branch"),
            tracked=repo["id"] in tracked_ids,
        )
        for repo in sorted(live, key=lambda r: r["full_name"])
    ]


async def add_repos(
    tenant_id: uuid.UUID,
    installation_id: int,
    github_ids: list[int],
    session: AsyncSession,
) -> Sequence[Repository]:
    """Add specific granted repos to a workspace. Explicit adds resurrect removals."""
    installation, _ = await _require_link(tenant_id, installation_id, session)

    github = GitHubClient()
    try:
        live = await github.list_repos(installation_id)
        live_by_id = {repo["id"]: repo for repo in live}
        unknown = set(github_ids) - set(live_by_id)
        if unknown:
            raise LinkError("Some repositories are not granted to this installation")

        repos_data = [live_by_id[github_id] for github_id in github_ids]
        await sync_repos(tenant_id, installation, repos_data, session)

        repo_result = await session.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.github_id.in_(github_ids),
            )
        )
        rows = repo_result.scalars().all()
        await discover_repo_environments(tenant_id, installation, rows, session, github=github)
    finally:
        await github.close()

    await session.commit()
    return rows


async def remove_repo(tenant_id: uuid.UUID, repo_id: uuid.UUID, session: AsyncSession) -> None:
    """Soft-delete a repo from one workspace. Removal is sticky against webhook re-adds."""
    result = await session.execute(
        select(Repository).where(Repository.id == repo_id, Repository.tenant_id == tenant_id)
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise LinkError("Repository not found in this workspace")
    repo.removed_at = datetime.now(UTC)
    await session.commit()


async def discover_repo_environments(
    tenant_id: uuid.UUID,
    installation: GitHubInstallation,
    repos: Sequence[Repository],
    session: AsyncSession,
    github: GitHubClient | None = None,
) -> None:
    """Fetch and record each repo's environments, reusing a client when given one."""
    owns_client = github is None
    client = github or GitHubClient()
    try:
        for repo in repos:
            owner, name = repo.full_name.split("/", 1)
            envs = await client.list_environments(owner, name, installation.installation_id)
            await discover_environments(tenant_id, repo, envs, session)
    finally:
        if owns_client:
            await client.close()


async def sync_repos(
    tenant_id: uuid.UUID,
    installation: GitHubInstallation,
    repos_data: list[dict],
    session: AsyncSession,
    *,
    respect_removed: bool = False,
) -> None:
    """Upsert repo rows for one workspace.

    With respect_removed=True (webhook syncs), rows a user deliberately removed
    stay removed; without it (explicit user actions), the upsert resurrects.
    """
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
                where=Repository.removed_at.is_(None) if respect_removed else None,
            )
        )
        await session.execute(stmt)
    await session.flush()
