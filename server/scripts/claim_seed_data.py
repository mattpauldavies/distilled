"""Assign the seed tenant's demo data to your personal Clerk user.

If you've already logged in locally, an owner membership is added to the seed
tenant (and the seed tenant becomes your last-active). If you haven't logged
in yet, a placeholder user + owner membership is created so your first login
resolves to the seed tenant automatically.

Usage:
    cd server && PYTHONPATH=. poetry run python scripts/claim_seed_data.py <clerk_user_id>

Your Clerk user ID is visible in the Clerk dashboard, or in the JWT payload as
the "sub" claim.
"""

import asyncio
import sys
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User

SEED_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _ensure_seed_owner(user_id: UUID, session) -> bool:
    existing = await session.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == SEED_TENANT_ID, TenantUser.user_id == user_id
        )
    )
    membership = existing.scalar_one_or_none()
    if membership is not None:
        if membership.role != "owner":
            membership.role = "owner"
            return True
        return False

    # Demote any existing owner of the seed tenant first — we maintain the
    # one-owner-per-tenant invariant.
    current_owner = await session.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == SEED_TENANT_ID, TenantUser.role == "owner"
        )
    )
    co = current_owner.scalar_one_or_none()
    if co is not None:
        co.role = "member"

    session.add(
        TenantUser(
            id=uuid.uuid4(),
            tenant_id=SEED_TENANT_ID,
            user_id=user_id,
            role="owner",
        )
    )
    return True


async def main(clerk_user_id: str) -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        tenant = await session.get(Tenant, SEED_TENANT_ID)
        if tenant is None:
            print("Error: seed tenant does not exist. Run `make migrate` first.")
            await engine.dispose()
            sys.exit(1)

        result = await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                id=uuid.uuid4(),
                clerk_user_id=clerk_user_id,
                last_active_tenant_id=SEED_TENANT_ID,
            )
            session.add(user)
            await session.flush()
            await _ensure_seed_owner(user.id, session)
            await session.commit()
            print(f"✓ Created user {clerk_user_id} as owner of seed tenant (GitHub data will backfill on first login).")
            await engine.dispose()
            return

        changed = await _ensure_seed_owner(user.id, session)
        user.last_active_tenant_id = SEED_TENANT_ID
        await session.commit()
        if changed:
            print(f"✓ Granted user {clerk_user_id} owner of seed tenant.")
        else:
            print(f"User {clerk_user_id} is already owner of the seed tenant. Set as active.")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("Usage: python scripts/claim_seed_data.py <clerk_user_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1].strip()))
