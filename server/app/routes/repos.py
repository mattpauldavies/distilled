import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.middleware.tenant import get_tenant_id
from app.models.repository import Repository
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.repos import RepoResponse
from app.services.pagination import paginate

router = APIRouter(prefix="/repos")


@router.get("")
async def list_repos(
    pagination: PaginationParams = Depends(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[RepoResponse]:
    stmt = (
        select(Repository)
        .where(Repository.tenant_id == tenant_id)
        .order_by(Repository.full_name)
    )
    return await paginate(session, stmt, pagination, RepoResponse)
