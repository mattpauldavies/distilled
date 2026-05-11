import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User

if TYPE_CHECKING:
    from app.services.clerk_service import ClerkJWTVerifier

logger = logging.getLogger(__name__)


async def _backfill_github_data(
    user: User,
    verifier: "ClerkJWTVerifier",
    session: AsyncSession,
) -> None:
    """Fill in github_username / github_account_id from Clerk on a follow-up login.

    We deliberately do not touch any tenant.slug here: in the multi-tenant world
    there's no single tenant for which the user's GitHub identity is canonical.
    Slug is set once at user creation time on the auto-provisioned tenant.
    """
    try:
        profile = await verifier.get_user(user.clerk_user_id)
        for account in profile.get("external_accounts", []):
            if account.get("provider") != "oauth_github":
                continue
            user.github_username = account.get("username")
            provider_user_id = account.get("provider_user_id")
            if provider_user_id:
                try:
                    user.github_account_id = int(provider_user_id)
                except (ValueError, TypeError):
                    pass
            await session.commit()
            logger.info("clerk_api: backfilled github data for %s", user.clerk_user_id)
            return
    except Exception as exc:
        logger.warning("clerk_api: backfill failed for %s: %s", user.clerk_user_id, exc)


async def get_or_create_user(
    claims: dict,
    session: AsyncSession,
    verifier: "ClerkJWTVerifier | None" = None,
) -> User:
    """Resolve the User for a Clerk JWT.

    Idempotent. On first call for a clerk_user_id, provisions a Tenant + User +
    owner TenantUser in one transaction, and points the user's last_active
    tenant at the new tenant. On subsequent calls, returns the existing user
    and best-effort-backfills missing GitHub fields.
    """
    clerk_user_id: str = claims["sub"]

    result = await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()

    if user is not None:
        if user.github_account_id is None and verifier is not None:
            await _backfill_github_data(user, verifier, session)
        return user

    # First login: provision tenant + user + owner membership.
    email: str | None = claims.get("email")
    github_username: str | None = None
    github_account_id: int | None = None

    if verifier is not None:
        try:
            profile = await verifier.get_user(clerk_user_id)
            for account in profile.get("external_accounts", []):
                if account.get("provider") == "oauth_github":
                    github_username = account.get("username")
                    provider_user_id = account.get("provider_user_id")
                    if provider_user_id:
                        try:
                            github_account_id = int(provider_user_id)
                        except (ValueError, TypeError):
                            pass
                    break
        except Exception as exc:
            logger.warning("clerk_api: failed to fetch profile for %s: %s", clerk_user_id, exc)

    tenant_name = github_username or clerk_user_id
    tenant = Tenant(
        id=uuid.uuid4(),
        name=tenant_name,
        slug=github_username,
    )
    session.add(tenant)
    await session.flush()

    user = User(
        id=uuid.uuid4(),
        clerk_user_id=clerk_user_id,
        email=email,
        github_username=github_username,
        github_account_id=github_account_id,
        last_active_tenant_id=tenant.id,
    )
    session.add(user)
    await session.flush()

    membership = TenantUser(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        role="owner",
    )
    session.add(membership)

    try:
        await session.flush()
        await session.commit()
    except IntegrityError:
        # Concurrent request already created this user — re-query
        await session.rollback()
        result = await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
        user = result.scalar_one()

    return user
