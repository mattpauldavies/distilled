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
from app.schemas.repos import RepoResponse, UpdateRepoRequest
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


@router.patch("/{repo_id}", response_model=RepoResponse)
async def update_repo(
    repo_id: uuid.UUID,
    body: UpdateRepoRequest,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> RepoResponse:
    """Change what counts as a deployment for one repo."""
    result = await session.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.tenant_id == current.tenant_id,
            Repository.removed_at.is_(None),
        )
    )
    # id is the primary key, so this matches at most one row.
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    repo.deployment_source = body.deployment_source
    await session.commit()
    return RepoResponse.model_validate(repo)


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
