import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_event import SOURCE_RELEASE, ProductionDeploymentEvent
from app.models.repository import Repository
from app.services.attribution_service import attribute_prs_to_deployment
from app.services.webhook_service import (
    SKIPPED,
    parse_datetime,
    parse_datetime_optional,
    register_handler,
    validate_github_url,
)

logger = logging.getLogger(__name__)

# A release has no environment — publishing one is the act of shipping.
RELEASE_ENVIRONMENT_NAME = "release"


@register_handler("release")
async def handle_release_event(payload: dict, session: AsyncSession) -> str | None:
    # `published` is the only action that marks a release as shipped: `created`
    # fires when a draft is saved and never fires again on publication.
    if payload.get("action") != "published":
        return SKIPPED

    release = payload["release"]
    if release.get("draft") or release.get("prerelease"):
        return SKIPPED

    repo_data = payload["repository"]

    # One Repository row per workspace tracking this GitHub repo.
    result = await session.execute(select(Repository).where(Repository.github_id == repo_data["id"]))
    repos = result.scalars().all()
    if not repos:
        logger.warning("repo not found github_id=%s", repo_data["id"])
        return SKIPPED

    created_at = parse_datetime(release.get("created_at", ""))
    published_at = parse_datetime_optional(release.get("published_at")) or created_at

    handled = False
    for repo in repos:
        if repo.deployment_source != SOURCE_RELEASE:
            logger.info(
                "repo_not_tracking_releases repo=%s tenant=%s — skipping",
                repo.full_name,
                repo.tenant_id,
            )
            continue

        dep_id = uuid.uuid4()
        stmt = (
            insert(ProductionDeploymentEvent)
            .values(
                id=dep_id,
                tenant_id=repo.tenant_id,
                repo_id=repo.id,
                environment_name=RELEASE_ENVIRONMENT_NAME,
                deployment_id=release["id"],
                source=SOURCE_RELEASE,
                started_at=created_at,
                completed_at=published_at,
                deployed_at=published_at,
                html_url=validate_github_url(release.get("html_url", "")),
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "source", "deployment_id"],
            )
        )
        insert_result = await session.execute(stmt)
        await session.flush()
        handled = True

        if insert_result.rowcount == 0:  # type: ignore[attr-defined]
            logger.info(
                "duplicate release_id=%s for tenant=%s, skipping",
                release["id"],
                repo.tenant_id,
            )
            continue

        dep_result = await session.execute(
            select(ProductionDeploymentEvent).where(
                ProductionDeploymentEvent.id == dep_id,
            )
        )
        await attribute_prs_to_deployment(dep_result.scalar_one(), repo, session)

    return None if handled else SKIPPED
