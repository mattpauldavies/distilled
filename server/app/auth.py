import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services.clerk_service import ClerkJWTVerifier
from app.services.user_service import get_or_create_user_and_tenant

_bearer_scheme = HTTPBearer()
verifier = ClerkJWTVerifier()


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    clerk_user_id: str


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    claims = await verifier.verify_token(credentials.credentials)
    user, tenant = await get_or_create_user_and_tenant(claims, session)
    if user is None or tenant is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return CurrentUser(
        user_id=user.id,
        tenant_id=tenant.id,
        clerk_user_id=user.clerk_user_id,
    )
