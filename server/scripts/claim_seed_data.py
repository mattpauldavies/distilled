"""Assign the seed tenant's demo data to your personal Clerk user.

If you've already logged in locally, your user row is moved to the seed tenant.
If you haven't logged in yet, a placeholder user row is created so your first
login resolves to the seed tenant automatically.

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
from app.models.user import User

SEED_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


async def main(clerk_user_id: str) -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Verify seed tenant exists
        tenant = await session.get(Tenant, SEED_TENANT_ID)
        if tenant is None:
            print("Error: seed tenant does not exist. Run `make migrate` first.")
            await engine.dispose()
            sys.exit(1)

        # Look up existing user
        result = await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
        user = result.scalar_one_or_none()

        if user is not None:
            if user.tenant_id == SEED_TENANT_ID:
                print(f"User {clerk_user_id} is already on the seed tenant. Nothing to do.")
                await engine.dispose()
                return

            old_tenant_id = user.tenant_id
            user.tenant_id = SEED_TENANT_ID
            await session.commit()
            print(f"✓ Moved user {clerk_user_id} from tenant {old_tenant_id} → seed tenant.")
        else:
            session.add(
                User(
                    id=uuid.uuid4(),
                    clerk_user_id=clerk_user_id,
                    tenant_id=SEED_TENANT_ID,
                )
            )
            await session.commit()
            print(f"✓ Created user {clerk_user_id} on seed tenant (GitHub data will backfill on first login).")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("Usage: python scripts/claim_seed_data.py <clerk_user_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1].strip()))
