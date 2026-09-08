import uuid

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.middleware.tenant import get_tenant_id
from app.models.repository import Repository


async def get_verified_repo(
    repo_id: uuid.UUID = Query(...),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> Repository:
    result = await session.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.tenant_id == tenant_id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo
