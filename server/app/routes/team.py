"""Owner-only routes for managing tenant membership and tenant settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_auth, require_owner
from app.db import get_session
from app.models.tenant import Tenant
from app.schemas.team import (
    MemberResponse,
    PendingInvitationResponse,
    RenameTenantRequest,
    TeamResponse,
    TenantSummaryResponse,
)
from app.services import membership_service

router = APIRouter(prefix="/team")


async def _load_tenant(tenant_id: uuid.UUID, session: AsyncSession) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("", response_model=TeamResponse)
async def get_team(
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> TeamResponse:
    tenant = await _load_tenant(current.tenant_id, session)
    members = await membership_service.list_members(current.tenant_id, session)

    # Pending invitations are populated in Phase 4 (invitation_service).
    # Returning [] keeps the contract stable and the frontend can already
    # render the "no pending" empty state.
    pending: list[PendingInvitationResponse] = []

    return TeamResponse(
        tenant=TenantSummaryResponse(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            role=current.role,
        ),
        rename_prompt_dismissed=tenant.rename_prompt_dismissed,
        members=[
            MemberResponse(
                user_id=m.user_id,
                email=m.email,
                github_username=m.github_username,
                role=m.role,  # type: ignore[arg-type]
            )
            for m in members
        ],
        pending_invitations=pending,
    )


@router.patch("", response_model=TenantSummaryResponse)
async def update_team(
    body: RenameTenantRequest,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> TenantSummaryResponse:
    if body.name is None and body.rename_prompt_dismissed is None:
        raise HTTPException(status_code=400, detail="No changes requested")

    if body.name is not None:
        try:
            await membership_service.rename_tenant(current.tenant_id, body.name, session)
        except membership_service.InvariantViolation as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.rename_prompt_dismissed is True:
        await membership_service.dismiss_rename_prompt(current.tenant_id, session)

    tenant = await _load_tenant(current.tenant_id, session)
    return TenantSummaryResponse(
        id=tenant.id, name=tenant.name, slug=tenant.slug, role=current.role
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: uuid.UUID,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> None:
    if user_id == current.user_id:
        raise HTTPException(
            status_code=400,
            detail="Owners cannot remove themselves; transfer ownership first",
        )
    try:
        await membership_service.remove_member(current.tenant_id, user_id, session)
    except membership_service.NotAMemberError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except membership_service.InvariantViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/members/{user_id}/transfer", status_code=status.HTTP_204_NO_CONTENT)
async def transfer_ownership(
    user_id: uuid.UUID,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await membership_service.transfer_ownership(
            current.tenant_id,
            current_owner_id=current.user_id,
            new_owner_id=user_id,
            session=session,
        )
    except membership_service.NotAMemberError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except membership_service.InvariantViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    current: CurrentUser = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> None:
    """A member leaves the active tenant. Owners must transfer or delete instead."""
    try:
        await membership_service.leave_tenant(current.tenant_id, current.user_id, session)
    except membership_service.NotAMemberError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except membership_service.InvariantViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete the active tenant. Only allowed when the owner is the sole user."""
    try:
        await membership_service.delete_tenant(current.tenant_id, session)
    except membership_service.InvariantViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
