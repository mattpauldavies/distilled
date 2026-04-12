import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services.clerk_service import ClerkJWTVerifier
from app.services.user_service import get_or_create_user_and_tenant

verifier = ClerkJWTVerifier()


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    clerk_user_id: str


async def require_auth(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Verify a Clerk RS256 JWT from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    claims = await verifier.verify_token(token)
    user, tenant = await get_or_create_user_and_tenant(claims, session, verifier)
    return CurrentUser(
        user_id=user.id,
        tenant_id=tenant.id,
        clerk_user_id=user.clerk_user_id,
    )
