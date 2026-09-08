import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.middleware.repo import get_verified_repo
from app.middleware.tenant import get_tenant_id
from app.models.deployment_attribution import DeploymentAttribution
from app.models.deployment_event import ProductionDeploymentEvent
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.pull_requests import (
    DeploymentSummary,
    PullRequestDetailResponse,
    PullRequestResponse,
)
from app.services.pagination import paginate

router = APIRouter(prefix="/pull-requests")


@router.get("")
async def list_pull_requests(
    pagination: PaginationParams = Depends(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
) -> PaginatedResponse[PullRequestResponse]:
    base = select(PullRequest).where(
        PullRequest.tenant_id == tenant_id,
        PullRequest.repo_id == repo.id,
    )
    if since:
        base = base.where(PullRequest.merged_at >= since)
    if until:
        base = base.where(PullRequest.merged_at <= until)

    stmt = base.order_by(PullRequest.merged_at.desc())
    return await paginate(session, stmt, pagination, PullRequestResponse)


@router.get("/{pr_id}")
async def get_pull_request(
    pr_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> PullRequestDetailResponse:
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.id == pr_id,
            PullRequest.tenant_id == tenant_id,
        )
    )
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Pull request not found")

    # Find linked deployment
    dep_result = await session.execute(
        select(ProductionDeploymentEvent)
        .join(DeploymentAttribution, DeploymentAttribution.deployment_id == ProductionDeploymentEvent.id)
        .where(
            DeploymentAttribution.pr_id == pr_id,
            ProductionDeploymentEvent.tenant_id == tenant_id,
        )
        .order_by(ProductionDeploymentEvent.deployed_at.desc())
        .limit(1)
    )
    dep = dep_result.scalar_one_or_none()

    detail = PullRequestDetailResponse.model_validate(pr)
    if dep:
        detail.deployment = DeploymentSummary.model_validate(dep)
    return detail
