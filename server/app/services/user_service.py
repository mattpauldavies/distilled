import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
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


async def get_or_create_user_and_tenant(
    claims: dict,
    session: AsyncSession,
    verifier: "ClerkJWTVerifier | None" = None,
) -> tuple[User, Tenant]:
    """
    Idempotent. On first call for a clerk_user_id, creates Tenant + User in one
    transaction. On subsequent calls, returns the existing records.

    Returns (user, tenant).
    """
    clerk_user_id: str = claims["sub"]

    result = await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()

    if user is not None:
        tenant_result = await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one()
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
        tenant_id=tenant.id,
    )
    session.add(user)

    try:
        await session.flush()
        await session.commit()
    except IntegrityError:
        # Concurrent request already created this user — re-query
        await session.rollback()
        result = await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
        user = result.scalar_one()
        tenant_result = await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one()

    return user, tenant
