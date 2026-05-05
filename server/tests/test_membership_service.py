import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.membership_service import (
    InvariantViolation,
    NotAMemberError,
    delete_tenant,
    leave_tenant,
    list_members,
    remove_member,
    rename_tenant,
    transfer_ownership,
)


def _membership(tenant_id: uuid.UUID, user_id: uuid.UUID, role: str) -> TenantUser:
    return TenantUser(id=uuid.uuid4(), tenant_id=tenant_id, user_id=user_id, role=role)


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    return session


# --- list_members ---


@pytest.mark.asyncio
async def test_list_members_returns_owner_and_members():
    session = _mock_session()
    tenant_id = uuid.uuid4()
    owner_id, member_id = uuid.uuid4(), uuid.uuid4()

    session.execute = AsyncMock(
        return_value=_scalars(
            [
                (_membership(tenant_id, owner_id, "owner"), "anna@x", "anna"),
                (_membership(tenant_id, member_id, "member"), "ravi@x", "ravi"),
            ]
        )
    )
    # list_members uses .all() on Result, not scalars().all()
    session.execute.return_value.all = MagicMock(
        return_value=[
            (_membership(tenant_id, owner_id, "owner"), "anna@x", "anna"),
            (_membership(tenant_id, member_id, "member"), "ravi@x", "ravi"),
        ]
    )

    members = await list_members(tenant_id, session)

    assert len(members) == 2
    by_id = {m.user_id: m for m in members}
    assert by_id[owner_id].role == "owner"
    assert by_id[member_id].role == "member"
    assert by_id[owner_id].email == "anna@x"
    assert by_id[owner_id].github_username == "anna"


# --- remove_member ---


@pytest.mark.asyncio
async def test_remove_member_deletes_membership():
    session = _mock_session()
    tenant_id, member_id = uuid.uuid4(), uuid.uuid4()
    membership = _membership(tenant_id, member_id, "member")

    session.execute = AsyncMock(return_value=_scalar(membership))

    await remove_member(tenant_id, member_id, session)

    session.delete.assert_awaited_once_with(membership)
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_remove_member_refuses_owner():
    session = _mock_session()
    tenant_id, owner_id = uuid.uuid4(), uuid.uuid4()
    membership = _membership(tenant_id, owner_id, "owner")
    session.execute = AsyncMock(return_value=_scalar(membership))

    with pytest.raises(InvariantViolation):
        await remove_member(tenant_id, owner_id, session)
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_non_member_raises():
    session = _mock_session()
    session.execute = AsyncMock(return_value=_scalar(None))

    with pytest.raises(NotAMemberError):
        await remove_member(uuid.uuid4(), uuid.uuid4(), session)


# --- transfer_ownership ---


@pytest.mark.asyncio
async def test_transfer_ownership_swaps_roles():
    session = _mock_session()
    tenant_id = uuid.uuid4()
    owner_id, member_id = uuid.uuid4(), uuid.uuid4()
    owner_row = _membership(tenant_id, owner_id, "owner")
    member_row = _membership(tenant_id, member_id, "member")

    session.execute = AsyncMock(
        side_effect=[_scalar(owner_row), _scalar(member_row)]
    )

    await transfer_ownership(tenant_id, current_owner_id=owner_id, new_owner_id=member_id, session=session)

    assert owner_row.role == "member"
    assert member_row.role == "owner"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_transfer_ownership_to_non_member_raises():
    session = _mock_session()
    tenant_id = uuid.uuid4()
    owner_row = _membership(tenant_id, uuid.uuid4(), "owner")

    session.execute = AsyncMock(side_effect=[_scalar(owner_row), _scalar(None)])

    with pytest.raises(NotAMemberError):
        await transfer_ownership(
            tenant_id,
            current_owner_id=owner_row.user_id,
            new_owner_id=uuid.uuid4(),
            session=session,
        )


@pytest.mark.asyncio
async def test_transfer_ownership_when_caller_not_owner_raises():
    session = _mock_session()
    tenant_id = uuid.uuid4()
    not_owner = _membership(tenant_id, uuid.uuid4(), "member")

    session.execute = AsyncMock(return_value=_scalar(not_owner))

    with pytest.raises(InvariantViolation):
        await transfer_ownership(
            tenant_id,
            current_owner_id=not_owner.user_id,
            new_owner_id=uuid.uuid4(),
            session=session,
        )


# --- leave_tenant ---


@pytest.mark.asyncio
async def test_leave_tenant_member_removes_membership():
    session = _mock_session()
    tenant_id, member_id = uuid.uuid4(), uuid.uuid4()
    membership = _membership(tenant_id, member_id, "member")
    session.execute = AsyncMock(return_value=_scalar(membership))

    await leave_tenant(tenant_id, member_id, session)

    session.delete.assert_awaited_once_with(membership)


@pytest.mark.asyncio
async def test_leave_tenant_owner_with_others_raises():
    session = _mock_session()
    tenant_id, owner_id = uuid.uuid4(), uuid.uuid4()
    owner_row = _membership(tenant_id, owner_id, "owner")

    count_result = MagicMock()
    count_result.scalar_one.return_value = 2  # owner + 1 member

    session.execute = AsyncMock(side_effect=[_scalar(owner_row), count_result])

    with pytest.raises(InvariantViolation):
        await leave_tenant(tenant_id, owner_id, session)
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_leave_tenant_owner_alone_falls_through_to_delete_path():
    """Owner who is the sole user must use delete_tenant, not leave."""
    session = _mock_session()
    tenant_id, owner_id = uuid.uuid4(), uuid.uuid4()
    owner_row = _membership(tenant_id, owner_id, "owner")

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    session.execute = AsyncMock(side_effect=[_scalar(owner_row), count_result])

    with pytest.raises(InvariantViolation):
        await leave_tenant(tenant_id, owner_id, session)


# --- delete_tenant ---


@pytest.mark.asyncio
async def test_delete_tenant_with_sole_user_succeeds():
    session = _mock_session()
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="acme")

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    session.execute = AsyncMock(side_effect=[count_result, _scalar(tenant)])

    await delete_tenant(tenant_id, session)
    session.delete.assert_awaited_once_with(tenant)


@pytest.mark.asyncio
async def test_delete_tenant_with_other_members_raises():
    session = _mock_session()
    tenant_id = uuid.uuid4()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 2

    session.execute = AsyncMock(return_value=count_result)

    with pytest.raises(InvariantViolation):
        await delete_tenant(tenant_id, session)
    session.delete.assert_not_awaited()


# --- rename_tenant ---


@pytest.mark.asyncio
async def test_rename_tenant_updates_name():
    session = _mock_session()
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="anna's tenant")
    session.execute = AsyncMock(return_value=_scalar(tenant))

    updated = await rename_tenant(tenant_id, "Acme Engineering", session)

    assert updated.name == "Acme Engineering"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_rename_tenant_rejects_blank():
    session = _mock_session()
    with pytest.raises(InvariantViolation):
        await rename_tenant(uuid.uuid4(), "   ", session)


@pytest.mark.asyncio
async def test_rename_tenant_strips_whitespace():
    session = _mock_session()
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="old")
    session.execute = AsyncMock(return_value=_scalar(tenant))

    updated = await rename_tenant(tenant_id, "  Acme  ", session)
    assert updated.name == "Acme"
