"""Remove all demo data seeded by seed_demo.py.

Usage:
    cd server && PYTHONPATH=. poetry run python scripts/reset_demo.py
"""

import asyncio
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.deployment_attribution import DeploymentAttribution
from app.models.deployment_event import ProductionDeploymentEvent
from app.models.environment import Environment
from app.models.github_installation import GitHubInstallation
from app.models.metrics import (
    DeploymentDailyMetric,
    LeadTimeWeeklyMetric,
    MetricsRefreshLog,
    PRCycleTimeWeeklyMetric,
    PRThroughputWeeklyMetric,
)
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.user import User

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


async def main() -> None:
    if settings.environment == "production":
        print("FATAL: refusing to run reset script against production database")
        return
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Find the demo installation by sentinel value
        result = await session.execute(
            select(GitHubInstallation).where(
                GitHubInstallation.account_login == "acme-corp",
                GitHubInstallation.tenant_id == TENANT_ID,
            )
        )
        installation = result.scalar_one_or_none()

        if installation is None:
            print("No demo data found.")
            await engine.dispose()
            return

        installation_uuid = installation.id

        # Collect demo repo IDs (scoped to this installation)
        repo_result = await session.execute(
            select(Repository.id).where(Repository.installation_id == installation_uuid)
        )
        repo_ids = [row[0] for row in repo_result.all()]

        if repo_ids:
            # Collect deployment IDs for attribution deletion
            deploy_result = await session.execute(
                select(ProductionDeploymentEvent.id).where(ProductionDeploymentEvent.repo_id.in_(repo_ids))
            )
            deploy_ids = [row[0] for row in deploy_result.all()]

            # Delete in FK-safe order, scoped to demo repos/deployments
            if deploy_ids:
                await session.execute(
                    delete(DeploymentAttribution).where(DeploymentAttribution.deployment_id.in_(deploy_ids))
                )
            await session.execute(delete(DeploymentDailyMetric).where(DeploymentDailyMetric.repo_id.in_(repo_ids)))
            await session.execute(delete(LeadTimeWeeklyMetric).where(LeadTimeWeeklyMetric.repo_id.in_(repo_ids)))
            await session.execute(delete(PRCycleTimeWeeklyMetric).where(PRCycleTimeWeeklyMetric.repo_id.in_(repo_ids)))
            await session.execute(
                delete(PRThroughputWeeklyMetric).where(PRThroughputWeeklyMetric.repo_id.in_(repo_ids))
            )
            await session.execute(delete(MetricsRefreshLog).where(MetricsRefreshLog.repo_id.in_(repo_ids)))
            await session.execute(
                delete(ProductionDeploymentEvent).where(ProductionDeploymentEvent.repo_id.in_(repo_ids))
            )
            await session.execute(delete(PullRequest).where(PullRequest.repo_id.in_(repo_ids)))
            await session.execute(delete(Environment).where(Environment.repo_id.in_(repo_ids)))
            await session.execute(delete(Repository).where(Repository.id.in_(repo_ids)))

        # Delete the installation (but NOT the tenant — it's shared with dev)
        await session.execute(delete(GitHubInstallation).where(GitHubInstallation.id == installation_uuid))

        # Remove any users linked to the seed tenant (smoke test user, claimed users)
        user_result = await session.execute(delete(User).where(User.tenant_id == TENANT_ID))
        users_removed = user_result.rowcount

        await session.commit()
        print(f"✓ Demo data removed ({len(repo_ids)} repos, {users_removed} users).")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
