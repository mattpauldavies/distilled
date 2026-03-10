import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_attribution import DeploymentAttribution
from app.models.deployment_event import ProductionDeploymentEvent
from app.models.pull_request import PullRequest
from app.models.repository import Repository

logger = logging.getLogger(__name__)


async def attribute_prs_to_deployment(
    deployment: ProductionDeploymentEvent,
    repo: Repository,
    session: AsyncSession,
) -> None:
    # Find previous deployment for same repo
    result = await session.execute(
        select(ProductionDeploymentEvent)
        .where(
            ProductionDeploymentEvent.repo_id == repo.id,
            ProductionDeploymentEvent.deployed_at < deployment.deployed_at,
        )
        .order_by(ProductionDeploymentEvent.deployed_at.desc())
        .limit(1)
    )
    prev_deployment = result.scalar_one_or_none()

    if prev_deployment:
        window_start = prev_deployment.deployed_at
    else:
        window_start = deployment.deployed_at - timedelta(days=30)

    # Find PRs merged in window targeting default branch
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.repo_id == repo.id,
            PullRequest.base_ref == repo.default_branch,
            PullRequest.merged_at > window_start,
            PullRequest.merged_at <= deployment.deployed_at,
        )
    )
    prs = result.scalars().all()

    if not prs:
        logger.info("no PRs to attribute for deployment=%s", deployment.id)
        return

    for pr in prs:
        stmt = insert(DeploymentAttribution).values(
            deployment_id=deployment.id,
            pr_id=pr.id,
            tenant_id=deployment.tenant_id,
        ).on_conflict_do_nothing()
        await session.execute(stmt)

    logger.info("attributed %d PRs to deployment=%s", len(prs), deployment.id)
