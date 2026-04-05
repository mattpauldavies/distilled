import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
    """
    Authenticate the incoming request.

    Production: verifies a Clerk RS256 JWT from the Authorization header.

    Dev / smoke-test bypass: when CLERK_JWKS_URL is not configured and
    ENVIRONMENT is not 'production', returns the seed tenant CurrentUser
    without any token check. This allows local development and smoke tests
    to run without a real Clerk instance.
    """
    if not settings.clerk_jwks_url:
        if settings.environment == "production":
            raise HTTPException(status_code=503, detail="Auth not configured")
        # Dev bypass — return seed tenant
        seed_id = uuid.UUID(settings.seed_tenant_id)
        return CurrentUser(
            user_id=seed_id,
            tenant_id=seed_id,
            clerk_user_id="dev-bypass",
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Not authenticated")

    token = auth_header[7:]
    claims = await verifier.verify_token(token)
    user, tenant = await get_or_create_user_and_tenant(claims, session, verifier)
    return CurrentUser(
        user_id=user.id,
        tenant_id=tenant.id,
        clerk_user_id=user.clerk_user_id,
    )
