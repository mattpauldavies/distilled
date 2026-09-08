"""User-scoped routes that don't depend on an active tenant.

These endpoints are reached pre-tenant-resolution: the tenant switcher
needs the membership list before it can pick an active tenant, and
the invitation banner needs to surface invites for users with no
matching tenant context yet.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verifier
from app.db import get_session
from app.models.invitation import Invitation
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User
from app.schemas.me import (
    MyInvitationResponse,
    MyInvitationsListResponse,
    SetActiveTenantRequest,
    TenantMembershipResponse,
    TenantsListResponse,
)
from app.services import invitation_service
from app.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me")
_security = HTTPBearer(auto_error=False)


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Authenticate the request without resolving an active tenant.

    Used for tenant-agnostic endpoints like the membership list and the
    pending-invitations banner. The user may have zero memberships and
    these endpoints still need to function.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    claims = await verifier.verify_token(credentials.credentials)
    return await get_or_create_user(claims, session, verifier)


@router.get("/tenants", response_model=TenantsListResponse)
async def list_tenants(
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> TenantsListResponse:
    result = await session.execute(
        select(Tenant, TenantUser.role)
        .join(TenantUser, TenantUser.tenant_id == Tenant.id)
        .where(TenantUser.user_id == user.id)
        .order_by(Tenant.name)
    )
    return TenantsListResponse(
        items=[
            TenantMembershipResponse(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                role=role,  # type: ignore[arg-type]
            )
            for tenant, role in result.all()
        ]
    )


@router.post("/active-tenant", status_code=status.HTTP_204_NO_CONTENT)
async def set_active_tenant(
    body: SetActiveTenantRequest,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Persist the user's active-tenant choice from the switcher."""
    membership = await session.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == body.tenant_id, TenantUser.user_id == user.id
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member of that tenant")
    user.last_active_tenant_id = body.tenant_id
    await session.commit()


@router.get("/invitations", response_model=MyInvitationsListResponse)
async def list_my_invitations(
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> MyInvitationsListResponse:
    """Pending invitations whose email matches one of the user's verified GitHub emails."""
    emails = await verifier.get_user_emails(user.clerk_user_id)
    invitations = await invitation_service.list_pending_for_user_emails(emails, session=session)
    if not invitations:
        return MyInvitationsListResponse(items=[])

    tenant_ids = {inv.tenant_id for inv in invitations}
    inviter_ids = {inv.invited_by_user_id for inv in invitations if inv.invited_by_user_id}

    tenants = {
        t.id: t
        for t in (
            await session.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))
        ).scalars().all()
    }
    inviters = {
        u.id: u
        for u in (
            await session.execute(select(User).where(User.id.in_(inviter_ids)))
        ).scalars().all()
    }

    return MyInvitationsListResponse(
        items=[
            MyInvitationResponse(
                id=inv.id,
                tenant_id=inv.tenant_id,
                tenant_name=tenants[inv.tenant_id].name if inv.tenant_id in tenants else "",
                inviter_name=(
                    inviters[inv.invited_by_user_id].github_username
                    if inv.invited_by_user_id and inv.invited_by_user_id in inviters
                    else None
                ),
                expires_at=inv.expires_at,
            )
            for inv in invitations
        ]
    )


@router.post("/invitations/{invitation_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Accept a banner-matched invitation. Verifies the invitation's email is
    one of the user's verified Clerk emails before joining."""
    result = await session.execute(select(Invitation).where(Invitation.id == invitation_id))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invitation not found")

    emails = {e.lower() for e in await verifier.get_user_emails(user.clerk_user_id)}
    if inv.email.lower() not in emails:
        raise HTTPException(status_code=403, detail="Invitation email does not match your account")

    if inv.revoked_at is not None or inv.redeemed_at is not None:
        raise HTTPException(status_code=400, detail="Invitation is no longer redeemable")

    existing = await session.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == inv.tenant_id, TenantUser.user_id == user.id
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(
            TenantUser(
                id=uuid.uuid4(),
                tenant_id=inv.tenant_id,
                user_id=user.id,
                role="member",
            )
        )

    inv.redeemed_at = datetime.now(UTC)
    user.last_active_tenant_id = inv.tenant_id
    await session.commit()


@router.post("/invitations/{invitation_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Dismiss a pending invitation from the banner. Marks it revoked so it
    will not surface again. The invitation owner can re-issue if needed."""
    result = await session.execute(select(Invitation).where(Invitation.id == invitation_id))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invitation not found")

    emails = {e.lower() for e in await verifier.get_user_emails(user.clerk_user_id)}
    if inv.email.lower() not in emails:
        raise HTTPException(status_code=403, detail="Invitation email does not match your account")

    if inv.revoked_at is None and inv.redeemed_at is None:
        inv.revoked_at = datetime.now(UTC)
        await session.commit()
