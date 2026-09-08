import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_event import ProductionDeploymentEvent
from app.models.environment import Environment
from app.models.repository import Repository
from app.services.attribution_service import attribute_prs_to_deployment
from app.services.webhook_service import parse_datetime, register_handler, validate_github_url

logger = logging.getLogger(__name__)


@register_handler("deployment_status")
async def handle_deployment_status_event(payload: dict, session: AsyncSession) -> None:
    if payload.get("deployment_status", {}).get("state") != "success":
        return

    deployment = payload["deployment"]
    repo_data = payload["repository"]

    # Look up repo by GitHub ID — globally unique, tenant derived from repo
    result = await session.execute(select(Repository).where(Repository.github_id == repo_data["id"]))
    repo = result.scalar_one_or_none()
    if not repo:
        logger.warning("repo not found github_id=%s", repo_data["id"])
        return

    tenant_id = repo.tenant_id

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
    completed_at = parse_datetime(deployment_status.get("created_at", ""))
    started_at = parse_datetime(deployment.get("created_at", ""))
    deployed_at = completed_at or started_at

    # Insert deployment event
    dep_id = uuid.uuid4()
    stmt = (
        insert(ProductionDeploymentEvent)
        .values(
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
            html_url=validate_github_url(deployment_status.get("target_url", "")),
        )
        .on_conflict_do_nothing(
            index_elements=["tenant_id", "deployment_id"],
        )
    )
    insert_result = await session.execute(stmt)
    await session.flush()

    if insert_result.rowcount == 0:  # type: ignore[attr-defined]
        logger.info("duplicate deployment_id=%s, skipping", deployment["id"])
        return

    # Get the inserted event for attribution
    dep_result = await session.execute(
        select(ProductionDeploymentEvent).where(
            ProductionDeploymentEvent.id == dep_id,
        )
    )
    dep_event = dep_result.scalar_one()
    await attribute_prs_to_deployment(dep_event, repo, session)
