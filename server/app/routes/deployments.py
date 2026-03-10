import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.deployment_attribution import DeploymentAttribution
from app.db.models.deployment_event import ProductionDeploymentEvent
from app.db.models.pull_request import PullRequest
from app.middleware.tenant import get_tenant_id
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.deployments import DeploymentDetailResponse, DeploymentResponse
from app.schemas.pull_requests import PullRequestResponse

router = APIRouter(prefix="/deployments")


@router.get("")
async def list_deployments(
    pagination: PaginationParams = Depends(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
    repo_id: uuid.UUID | None = Query(None),
    environment: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
) -> PaginatedResponse[DeploymentResponse]:
    base = select(ProductionDeploymentEvent).where(
        ProductionDeploymentEvent.tenant_id == tenant_id
    )
    if repo_id:
        base = base.where(ProductionDeploymentEvent.repo_id == repo_id)
    if environment:
        base = base.where(ProductionDeploymentEvent.environment_name == environment)
    if since:
        base = base.where(ProductionDeploymentEvent.deployed_at >= since)
    if until:
        base = base.where(ProductionDeploymentEvent.deployed_at <= until)

    total_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    result = await session.execute(
        base.order_by(ProductionDeploymentEvent.deployed_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    deployments = result.scalars().all()

    return PaginatedResponse(
        items=[DeploymentResponse.model_validate(d) for d in deployments],
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.get("/{deployment_id}")
async def get_deployment(
    deployment_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> DeploymentDetailResponse:
    result = await session.execute(
        select(ProductionDeploymentEvent).where(
            ProductionDeploymentEvent.id == deployment_id,
            ProductionDeploymentEvent.tenant_id == tenant_id,
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")

    # Get attributed PRs
    pr_result = await session.execute(
        select(PullRequest)
        .join(DeploymentAttribution, DeploymentAttribution.pr_id == PullRequest.id)
        .where(DeploymentAttribution.deployment_id == deployment_id)
    )
    prs = pr_result.scalars().all()

    detail = DeploymentDetailResponse.model_validate(dep)
    detail.attributed_prs = [PullRequestResponse.model_validate(pr) for pr in prs]
    return detail
