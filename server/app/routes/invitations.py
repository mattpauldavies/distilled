"""Public-ish invitation routes: redemption only.

Authenticated by JWT (the user must be signed in to claim membership) but
NOT scoped by X-Tenant-Id — the tenant is the consequence of redemption,
not a precondition.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_session
from app.models.user import User
from app.schemas.me import RedeemRequest, RedeemResponse
from app.services import invitation_service

router = APIRouter(prefix="/invitations")


@router.post("/redeem", response_model=RedeemResponse)
async def redeem(
    body: RedeemRequest,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> RedeemResponse:
    try:
        tenant_id = await invitation_service.redeem_invitation(
            token=body.token, current_user_id=user.id, session=session
        )
    except invitation_service.InvitationStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.last_active_tenant_id = tenant_id
    await session.commit()
    return RedeemResponse(tenant_id=tenant_id)
