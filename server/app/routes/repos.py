import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.middleware.tenant import get_tenant_id
from app.models.repository import Repository
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.repos import RepoResponse

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
