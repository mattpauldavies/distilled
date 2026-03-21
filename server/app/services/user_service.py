import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User


async def get_or_create_user_and_tenant(
    claims: dict,
    session: AsyncSession,
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
        return user, tenant

    # Extract identity from claims
    email: str | None = claims.get("email")
    github_username: str | None = None
    github_account_id: int | None = None

    for account in claims.get("external_accounts", []):
        if account.get("provider") == "oauth_github":
            github_username = account.get("username")
            provider_user_id = account.get("provider_user_id")
            if provider_user_id:
                try:
                    github_account_id = int(provider_user_id)
                except (ValueError, TypeError):
                    pass
            break

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
    await session.flush()

    return user, tenant
