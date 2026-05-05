import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User
from app.services.clerk_service import ClerkJWTVerifier
from app.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)

verifier = ClerkJWTVerifier()
security = HTTPBearer(auto_error=False)

Role = Literal["owner", "member"]


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role
    clerk_user_id: str


def _parse_tenant_header(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-Tenant-Id header") from exc


async def _resolve_active_tenant(
    user: User,
    requested: uuid.UUID | None,
    session: AsyncSession,
) -> tuple[Tenant, Role] | None:
    """Resolve the tenant the request is operating against.

    If the client supplies X-Tenant-Id we honour it (after verifying membership).
    Otherwise we fall back to the user's last-active tenant. In either case we
    require an active TenantUser row; if none exists we return None and let the
    caller decide whether that's a 403 or 409.
    """
    target_id = requested or user.last_active_tenant_id
    if target_id is None:
        return None

    result = await session.execute(
        select(Tenant, TenantUser.role)
        .join(TenantUser, TenantUser.tenant_id == Tenant.id)
        .where(Tenant.id == target_id, TenantUser.user_id == user.id)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def _persist_last_active(user: User, tenant_id: uuid.UUID, session: AsyncSession) -> None:
    if user.last_active_tenant_id == tenant_id:
        return
    user.last_active_tenant_id = tenant_id
    try:
        await session.commit()
    except Exception as exc:
        logger.warning("auth: failed to persist last_active_tenant_id: %s", exc)
        await session.rollback()


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Verify a Clerk JWT and resolve the active tenant for this request.

    The active tenant is the value of `X-Tenant-Id` if present (and the user
    is a member of it), otherwise the user's last-active tenant. Membership
    is required either way.

    Raises:
        401 — Missing/invalid Authorization header
        403 — User is not a member of the requested tenant
        409 — User has no active tenant at all (no header, no last-active, or
              memberships have been removed)
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    requested_tenant_id = _parse_tenant_header(x_tenant_id)

    claims = await verifier.verify_token(credentials.credentials)
    user = await get_or_create_user(claims, session, verifier)

    resolved = await _resolve_active_tenant(user, requested_tenant_id, session)
    if resolved is None:
        if requested_tenant_id is not None:
            raise HTTPException(status_code=403, detail="Not a member of the requested tenant")
        raise HTTPException(status_code=409, detail="No active tenant for user")

    tenant, role = resolved
    await _persist_last_active(user, tenant.id, session)

    return CurrentUser(
        user_id=user.id,
        tenant_id=tenant.id,
        role=role,
        clerk_user_id=user.clerk_user_id,
    )


async def require_owner(current_user: CurrentUser = Depends(require_auth)) -> CurrentUser:
    """Owner-only guard. Use as a route dependency for /team/* mutations."""
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    return current_user
