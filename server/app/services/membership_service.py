"""Tenant membership management.

All routes that mutate membership funnel through this module so the
one-owner-per-tenant invariant has exactly one place that enforces it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User


class MembershipError(Exception):
    pass


class NotAMemberError(MembershipError):
    """Target user is not a member of the tenant."""


class InvariantViolation(MembershipError):
    """An operation would break a tenant invariant (owner removal, no-owner, etc.)."""


@dataclass
class MemberView:
    user_id: uuid.UUID
    email: str | None
    github_username: str | None
    role: str


async def _get_membership(
    tenant_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> TenantUser | None:
    result = await session.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == tenant_id, TenantUser.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _count_members(tenant_id: uuid.UUID, session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(TenantUser.id)).where(TenantUser.tenant_id == tenant_id)
    )
    return result.scalar_one()


async def list_members(tenant_id: uuid.UUID, session: AsyncSession) -> list[MemberView]:
    result = await session.execute(
        select(TenantUser, User.email, User.github_username)
        .join(User, User.id == TenantUser.user_id)
        .where(TenantUser.tenant_id == tenant_id)
        .order_by(TenantUser.role.desc(), User.github_username)
    )
    return [
        MemberView(user_id=m.user_id, email=email, github_username=username, role=m.role)
        for m, email, username in result.all()
    ]


async def remove_member(
    tenant_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> None:
    membership = await _get_membership(tenant_id, user_id, session)
    if membership is None:
        raise NotAMemberError(f"User {user_id} is not a member of tenant {tenant_id}")
    if membership.role == "owner":
        raise InvariantViolation(
            "Cannot remove the owner; transfer ownership or delete the tenant"
        )

    await session.delete(membership)
    await session.commit()


async def leave_tenant(
    tenant_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> None:
    membership = await _get_membership(tenant_id, user_id, session)
    if membership is None:
        raise NotAMemberError(f"User {user_id} is not a member of tenant {tenant_id}")
    if membership.role == "owner":
        # Owners always have to either transfer or delete; never leave.
        raise InvariantViolation(
            "Owners cannot leave; transfer ownership first, or delete the tenant if you are the sole user"
        )

    await session.delete(membership)
    await session.commit()


async def transfer_ownership(
    tenant_id: uuid.UUID,
    *,
    current_owner_id: uuid.UUID,
    new_owner_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    if current_owner_id == new_owner_id:
        raise InvariantViolation("Cannot transfer ownership to yourself")

    current = await _get_membership(tenant_id, current_owner_id, session)
    if current is None or current.role != "owner":
        raise InvariantViolation("Caller is not the current owner")

    target = await _get_membership(tenant_id, new_owner_id, session)
    if target is None:
        raise NotAMemberError(f"User {new_owner_id} is not a member of tenant {tenant_id}")

    # Demote then promote in the same transaction. The partial unique index
    # allows this two-statement swap because the demoted owner is no longer
    # 'owner' by the time the new owner is promoted (if the DB enforces
    # constraints at statement level — which it does on Postgres for a unique
    # index — the order matters).
    current.role = "member"
    await session.flush()
    target.role = "owner"
    await session.commit()


async def delete_tenant(tenant_id: uuid.UUID, session: AsyncSession) -> None:
    member_count = await _count_members(tenant_id, session)
    if member_count > 1:
        raise InvariantViolation(
            f"Tenant has {member_count} members; remove or transfer them before deletion"
        )

    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return  # idempotent

    # ON DELETE CASCADE handles every dependent row in one shot.
    await session.delete(tenant)
    await session.commit()


async def rename_tenant(
    tenant_id: uuid.UUID, new_name: str, session: AsyncSession
) -> Tenant:
    cleaned = (new_name or "").strip()
    if not cleaned:
        raise InvariantViolation("Tenant name cannot be blank")

    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise InvariantViolation(f"Tenant {tenant_id} does not exist")

    tenant.name = cleaned
    await session.commit()
    return tenant


async def dismiss_rename_prompt(tenant_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return
    tenant.rename_prompt_dismissed = True
    await session.commit()
