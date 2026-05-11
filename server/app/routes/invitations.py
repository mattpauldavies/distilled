"""Public-ish invitation routes: redemption only.

Authenticated by JWT (the user must be signed in to claim membership) but
NOT scoped by X-Tenant-Id — the tenant is the consequence of redemption,
not a precondition.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verifier
from app.db import get_session
from app.models.user import User
from app.schemas.me import RedeemRequest, RedeemResponse
from app.services import invitation_service
from app.services.user_service import get_or_create_user

router = APIRouter(prefix="/invitations")
_security = HTTPBearer(auto_error=False)


async def _require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    claims = await verifier.verify_token(credentials.credentials)
    return await get_or_create_user(claims, session, verifier)


@router.post("/redeem", response_model=RedeemResponse)
async def redeem(
    body: RedeemRequest,
    user: User = Depends(_require_user),
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
