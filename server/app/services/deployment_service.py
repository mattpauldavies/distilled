import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_event import ProductionDeploymentEvent
from app.models.environment import Environment
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.services.attribution_service import attribute_prs_to_deployment
from app.services.webhook_service import register_handler

logger = logging.getLogger(__name__)


@register_handler("deployment_status")
async def handle_deployment_status_event(payload: dict, session: AsyncSession) -> None:
    if payload.get("deployment_status", {}).get("state") != "success":
        return

    deployment = payload["deployment"]
    repo_data = payload["repository"]
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    # Look up repo
    result = await session.execute(
        select(Repository).where(
            Repository.tenant_id == tenant_id,
            Repository.github_id == repo_data["id"],
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        logger.warning("repo not found github_id=%s", repo_data["id"])
        return

    # Check if environment is production
    env_name = deployment["environment"]
    result = await session.execute(
        select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.repo_id == repo.id,
            Environment.name == env_name,
            Environment.is_production.is_(True),
        )
    )
    env = result.scalar_one_or_none()
    if not env:
        logger.info("non-prod environment=%s, skipping", env_name)
        return

    # Parse timestamps
    deployment_status = payload["deployment_status"]
    completed_at = _parse_dt(deployment_status.get("created_at", ""))
    started_at = _parse_dt(deployment.get("created_at", ""))
    deployed_at = completed_at or started_at

    # Insert deployment event
    dep_id = uuid.uuid4()
    stmt = insert(ProductionDeploymentEvent).values(
        id=dep_id,
        tenant_id=tenant_id,
        repo_id=repo.id,
        environment_name=env_name,
        deployment_id=deployment["id"],
        commit_sha=deployment.get("sha", ""),
        ref=deployment.get("ref", ""),
        started_at=started_at,
        completed_at=completed_at,
        deployed_at=deployed_at,
        html_url=deployment_status.get("target_url", ""),
    ).on_conflict_do_nothing(
        index_elements=["tenant_id", "deployment_id"],
    )
    result = await session.execute(stmt)
    await session.flush()

    if result.rowcount == 0:
        logger.info("duplicate deployment_id=%s, skipping", deployment["id"])
        return

    # Get the inserted event for attribution
    result = await session.execute(
        select(ProductionDeploymentEvent).where(
            ProductionDeploymentEvent.id == dep_id,
        )
    )
    dep_event = result.scalar_one()
    await attribute_prs_to_deployment(dep_event, repo, session)


@register_handler("pull_request")
async def handle_pull_request_event(payload: dict, session: AsyncSession) -> None:
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})

    if action != "closed" or not pr_data.get("merged"):
        return

    repo_data = payload["repository"]
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    # Look up repo
    result = await session.execute(
        select(Repository).where(
            Repository.tenant_id == tenant_id,
            Repository.github_id == repo_data["id"],
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        logger.warning("repo not found for PR, github_id=%s", repo_data["id"])
        return

    merged_at = _parse_dt(pr_data.get("merged_at", ""))
    stmt = insert(PullRequest).values(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        repo_id=repo.id,
        github_id=pr_data["id"],
        number=pr_data["number"],
        title=pr_data.get("title", ""),
        base_ref=pr_data.get("base", {}).get("ref", ""),
        merged_at=merged_at,
        merge_commit_sha=pr_data.get("merge_commit_sha", ""),
        head_sha=pr_data.get("head", {}).get("sha", ""),
        author_login=pr_data.get("user", {}).get("login", ""),
        html_url=pr_data.get("html_url", ""),
    ).on_conflict_do_update(
        index_elements=["tenant_id", "repo_id", "number"],
        set_={
            "title": pr_data.get("title", ""),
            "merged_at": merged_at,
            "merge_commit_sha": pr_data.get("merge_commit_sha", ""),
        },
    )
    await session.execute(stmt)


def _parse_dt(value: str) -> datetime:
    if not value:
        return datetime(2000, 1, 1)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
