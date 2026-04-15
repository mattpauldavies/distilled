import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services.clerk_service import ClerkJWTVerifier
from app.services.user_service import get_or_create_user_and_tenant

verifier = ClerkJWTVerifier()
security = HTTPBearer()


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    clerk_user_id: str


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Verify a Clerk RS256 JWT from the Authorization header."""
    token = credentials.credentials
    claims = await verifier.verify_token(token)
    user, tenant = await get_or_create_user_and_tenant(claims, session, verifier)
    return CurrentUser(
        user_id=user.id,
        tenant_id=tenant.id,
        clerk_user_id=user.clerk_user_id,
    )
