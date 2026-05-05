"""Owner-only routes for managing tenant membership and tenant settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_auth, require_owner
from app.db import get_session
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.team import (
    CreateInvitationRequest,
    CreateInvitationResponse,
    MemberResponse,
    PendingInvitationResponse,
    RenameTenantRequest,
    TeamResponse,
    TenantSummaryResponse,
)
from app.services import invitation_service, membership_service
from app.services.email_service import build_email_service

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
    pending_rows = await invitation_service.list_pending_for_tenant(
        tenant_id=current.tenant_id, session=session
    )
    pending = [
        PendingInvitationResponse(
            id=row.id,
            email=row.email,
            invited_at=row.created_at,
            expires_at=row.expires_at,
        )
        for row in pending_rows
    ]

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


async def _inviter_display_name(user_id: uuid.UUID, session: AsyncSession) -> str:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return "A teammate"
    return user.github_username or (user.email or "A teammate")


@router.post("/invitations", response_model=CreateInvitationResponse, status_code=201)
async def create_invitation(
    body: CreateInvitationRequest,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> CreateInvitationResponse:
    inviter_name = await _inviter_display_name(current.user_id, session)
    try:
        invitation = await invitation_service.create_invitation(
            tenant_id=current.tenant_id,
            inviter_user_id=current.user_id,
            inviter_display_name=inviter_name,
            email=body.email,
            session=session,
            email_service=build_email_service(),
        )
    except invitation_service.AlreadyMemberError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except invitation_service.DuplicateInvitationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except invitation_service.InvitationStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreateInvitationResponse(
        id=invitation.id, email=invitation.email, expires_at=invitation.expires_at
    )


@router.post("/invitations/{invitation_id}/resend", response_model=CreateInvitationResponse)
async def resend_invitation_route(
    invitation_id: uuid.UUID,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> CreateInvitationResponse:
    inviter_name = await _inviter_display_name(current.user_id, session)
    try:
        invitation = await invitation_service.resend_invitation(
            invitation_id=invitation_id,
            tenant_id=current.tenant_id,
            inviter_display_name=inviter_name,
            session=session,
            email_service=build_email_service(),
        )
    except invitation_service.InvitationStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreateInvitationResponse(
        id=invitation.id, email=invitation.email, expires_at=invitation.expires_at
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation_route(
    invitation_id: uuid.UUID,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await invitation_service.revoke_invitation(
            invitation_id=invitation_id, tenant_id=current.tenant_id, session=session
        )
    except invitation_service.InvitationStateError as exc:
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
