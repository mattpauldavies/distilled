import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.environment import Environment
from app.middleware.tenant import get_tenant_id
from app.schemas.environments import EnvironmentResponse, UpdateEnvironmentRequest

router = APIRouter(prefix="/environments")


@router.get("")
async def list_environments(
    repo_id: uuid.UUID | None = Query(None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> list[EnvironmentResponse]:
    query = select(Environment).where(Environment.tenant_id == tenant_id)
    if repo_id:
        query = query.where(Environment.repo_id == repo_id)
    query = query.order_by(Environment.name)

    result = await session.execute(query)
    envs = result.scalars().all()
    return [EnvironmentResponse.model_validate(e) for e in envs]


@router.patch("/{env_id}")
async def update_environment(
    env_id: uuid.UUID,
    body: UpdateEnvironmentRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> EnvironmentResponse:
    result = await session.execute(
        select(Environment).where(
            Environment.id == env_id,
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
