import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.environment import Environment
from app.models.repository import Repository
from app.middleware.tenant import get_tenant_id
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.repos import EnvironmentResponse, RepoResponse, UpdateEnvironmentRequest

router = APIRouter(prefix="/repos")


@router.get("")
async def list_repos(
    pagination: PaginationParams = Depends(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[RepoResponse]:
    base = select(Repository).where(Repository.tenant_id == tenant_id)

    total_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    result = await session.execute(
        base.order_by(Repository.full_name).offset(pagination.offset).limit(pagination.limit)
    )
    repos = result.scalars().all()

    return PaginatedResponse(
        items=[RepoResponse.model_validate(r) for r in repos],
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.get("/{repo_id}/environments")
async def list_environments(
    repo_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> list[EnvironmentResponse]:
    result = await session.execute(
        select(Environment).where(
            Environment.tenant_id == tenant_id,
            Environment.repo_id == repo_id,
        ).order_by(Environment.name)
    )
    envs = result.scalars().all()
    return [EnvironmentResponse.model_validate(e) for e in envs]


@router.patch("/{repo_id}/environments/{env_id}")
async def update_environment(
    repo_id: uuid.UUID,
    env_id: uuid.UUID,
    body: UpdateEnvironmentRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> EnvironmentResponse:
    result = await session.execute(
        select(Environment).where(
            Environment.id == env_id,
            Environment.repo_id == repo_id,
            Environment.tenant_id == tenant_id,
        )
    )
    env = result.scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")

    env.is_production = body.is_production
    await session.commit()
    await session.refresh(env)
    return EnvironmentResponse.model_validate(env)
