"""Workspace lifecycle routes.

Authenticated by JWT only — creating a workspace cannot depend on an active
workspace (the caller may have none).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_session
from app.models.user import User
from app.schemas.workspace import CreateWorkspaceRequest, WorkspaceResponse
from app.services import user_service

router = APIRouter(prefix="/workspaces")


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    try:
        tenant = await user_service.create_workspace(user, body.name, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WorkspaceResponse(id=tenant.id, name=tenant.name, role="owner")
