import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_owner
from app.db import get_session
from app.middleware.tenant import get_tenant_id
from app.models.repository import Repository
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.installation import AddReposRequest
from app.schemas.repos import RepoResponse
from app.services import installation_link_service
from app.services.installation_link_service import LinkError
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
        .where(Repository.tenant_id == tenant_id, Repository.removed_at.is_(None))
        .order_by(Repository.full_name)
    )
    return await paginate(session, stmt, pagination, RepoResponse)


@router.post("", response_model=list[RepoResponse], status_code=status.HTTP_201_CREATED)
async def add_repos(
    body: AddReposRequest,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> list[RepoResponse]:
    try:
        rows = await installation_link_service.add_repos(
            current.tenant_id, body.installation_id, body.github_ids, session
        )
    except LinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [RepoResponse.model_validate(row) for row in rows]


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_repo(
    repo_id: uuid.UUID,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await installation_link_service.remove_repo(current.tenant_id, repo_id, session)
    except LinkError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
