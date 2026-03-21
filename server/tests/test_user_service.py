import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.tenant import Tenant
from app.models.user import User
from app.services.user_service import get_or_create_user_and_tenant


def make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def mock_result(scalar_or_none=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_or_none
    result.scalar_one.return_value = scalar_or_none
    return result


TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

TEST_CLAIMS = {
    "sub": "user_clerk123",
    "email": "dev@example.com",
    "external_accounts": [
        {
            "provider": "oauth_github",
            "username": "devuser",
            "provider_user_id": "98765",
        }
    ],
}


@pytest.mark.asyncio
async def test_first_call_creates_tenant_and_user():
    """First call for a new clerk_user_id creates Tenant and User."""
    session = make_mock_session()
    # No existing user
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    user, tenant = await get_or_create_user_and_tenant(TEST_CLAIMS, session)

    # Should add tenant and user to session
    assert session.add.call_count == 2
    assert session.flush.call_count == 2

    # Check the created objects
    added_objects = [call.args[0] for call in session.add.call_args_list]
    tenant_obj = next(obj for obj in added_objects if isinstance(obj, Tenant))
    user_obj = next(obj for obj in added_objects if isinstance(obj, User))

    assert tenant_obj.name == "devuser"
    assert tenant_obj.slug == "devuser"
    assert user_obj.clerk_user_id == "user_clerk123"
    assert user_obj.email == "dev@example.com"
    assert user_obj.github_username == "devuser"
    assert user_obj.github_account_id == 98765


@pytest.mark.asyncio
async def test_second_call_returns_existing_records():
    """Second call for the same clerk_user_id returns existing records (idempotent)."""
    session = make_mock_session()

    existing_user = User(
        id=USER_ID,
        clerk_user_id="user_clerk123",
        email="dev@example.com",
        github_username="devuser",
        github_account_id=98765,
        tenant_id=TENANT_ID,
    )
    existing_tenant = Tenant(id=TENANT_ID, name="devuser", slug="devuser")

    # First execute returns existing user, second returns tenant
    session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=existing_user),
            mock_result(scalar_or_none=existing_tenant),
        ]
    )

    user, tenant = await get_or_create_user_and_tenant(TEST_CLAIMS, session)

    assert user.id == USER_ID
    assert tenant.id == TENANT_ID
    # No new objects should be added
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_clerk_id_when_no_github():
    """Tenant name falls back to clerk_user_id when GitHub account is absent."""
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    claims = {"sub": "user_nogh123", "email": "ngh@example.com", "external_accounts": []}
    user, tenant = await get_or_create_user_and_tenant(claims, session)

    added_objects = [call.args[0] for call in session.add.call_args_list]
    tenant_obj = next(obj for obj in added_objects if isinstance(obj, Tenant))
    assert tenant_obj.name == "user_nogh123"
    assert tenant_obj.slug is None


@pytest.mark.asyncio
async def test_handles_missing_external_accounts_key():
    """Claims without 'external_accounts' key are handled gracefully."""
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    claims = {"sub": "user_minimal"}
    user, tenant = await get_or_create_user_and_tenant(claims, session)

    added_objects = [call.args[0] for call in session.add.call_args_list]
    user_obj = next(obj for obj in added_objects if isinstance(obj, User))
    assert user_obj.github_account_id is None
    assert user_obj.github_username is None
    assert user_obj.email is None
