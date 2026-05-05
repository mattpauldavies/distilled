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
    tenant: Tenant,
    verifier: "ClerkJWTVerifier",
    session: AsyncSession,
) -> None:
    try:
        profile = await verifier.get_user(user.clerk_user_id)
        for account in profile.get("external_accounts", []):
            if account.get("provider") == "oauth_github":
                user.github_username = account.get("username")
                provider_user_id = account.get("provider_user_id")
                if provider_user_id:
                    try:
                        user.github_account_id = int(provider_user_id)
                    except (ValueError, TypeError):
                        pass
                if user.github_username and not tenant.slug:
                    tenant.slug = user.github_username
                    tenant.name = user.github_username
                await session.commit()
                logger.info("clerk_api: backfilled github data for %s", user.clerk_user_id)
                break
    except Exception as exc:
        logger.warning("clerk_api: backfill failed for %s: %s", user.clerk_user_id, exc)


async def _resolve_default_tenant(user: User, session: AsyncSession) -> Tenant | None:
    """Return the tenant a user should land on when they have no header preference.

    Order: their last-active tenant (if still a member), else any membership, else None.
    """
    if user.last_active_tenant_id is not None:
        result = await session.execute(
            select(Tenant)
            .join(TenantUser, TenantUser.tenant_id == Tenant.id)
            .where(Tenant.id == user.last_active_tenant_id, TenantUser.user_id == user.id)
        )
        tenant = result.scalar_one_or_none()
        if tenant is not None:
            return tenant

    result = await session.execute(
        select(Tenant)
        .join(TenantUser, TenantUser.tenant_id == Tenant.id)
        .where(TenantUser.user_id == user.id)
        .order_by(Tenant.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_user_and_tenant(
    claims: dict,
    session: AsyncSession,
    verifier: "ClerkJWTVerifier | None" = None,
) -> tuple[User, Tenant]:
    """
    Idempotent. On first call for a clerk_user_id, creates Tenant + User +
    owner TenantUser in one transaction. On subsequent calls, returns the
    existing user along with their default tenant.
    """
    clerk_user_id: str = claims["sub"]

    result = await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()

    if user is not None:
        tenant = await _resolve_default_tenant(user, session)
        if tenant is None:
            # User exists but every membership has been removed. The auth layer
            # surfaces this as a 409; we return the user with no tenant so the
            # caller can decide what to do.
            raise NoActiveTenantError(user_id=user.id)

        if user.github_account_id is None and verifier is not None:
            await _backfill_github_data(user, tenant, verifier, session)
        return user, tenant

    # Extract identity — email comes from the JWT, GitHub data from the Clerk API
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
        tenant = await _resolve_default_tenant(user, session)
        if tenant is None:
            raise NoActiveTenantError(user_id=user.id) from None

    return user, tenant


class NoActiveTenantError(Exception):
    """Raised when an authenticated user has no tenant memberships at all."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"User {user_id} has no tenant memberships")
        self.user_id = user_id
