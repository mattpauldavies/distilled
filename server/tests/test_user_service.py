import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User
from app.services.user_service import get_or_create_user


def make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def make_mock_verifier(github_username: str | None = "devuser", github_account_id: str | None = "98765") -> AsyncMock:
    verifier = AsyncMock()
    external_accounts = []
    if github_username or github_account_id:
        external_accounts = [
            {
                "provider": "oauth_github",
                "username": github_username,
                "provider_user_id": github_account_id,
            }
        ]
    verifier.get_user = AsyncMock(return_value={"external_accounts": external_accounts})
    return verifier


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
}


@pytest.mark.asyncio
async def test_first_call_provisions_tenant_user_and_owner_membership():
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))
    verifier = make_mock_verifier()

    user = await get_or_create_user(TEST_CLAIMS, session, verifier)

    # Tenant + User + owner TenantUser
    assert session.add.call_count == 3
    assert session.flush.call_count == 3
    session.commit.assert_called_once()

    added = [call.args[0] for call in session.add.call_args_list]
    tenant_obj = next(o for o in added if isinstance(o, Tenant))
    user_obj = next(o for o in added if isinstance(o, User))
    membership_obj = next(o for o in added if isinstance(o, TenantUser))

    assert tenant_obj.name == "devuser"
    assert tenant_obj.slug == "devuser"
    assert user_obj is user
    assert user_obj.clerk_user_id == "user_clerk123"
    assert user_obj.email == "dev@example.com"
    assert user_obj.github_username == "devuser"
    assert user_obj.github_account_id == 98765
    assert user_obj.last_active_tenant_id == tenant_obj.id
    assert membership_obj.role == "owner"
    assert membership_obj.tenant_id == tenant_obj.id
    assert membership_obj.user_id == user_obj.id

    verifier.get_user.assert_called_once_with("user_clerk123")


@pytest.mark.asyncio
async def test_second_call_returns_existing_user_without_clerk_lookup():
    session = make_mock_session()
    verifier = make_mock_verifier()

    existing_user = User(
        id=USER_ID,
        clerk_user_id="user_clerk123",
        email="dev@example.com",
        github_username="devuser",
        github_account_id=98765,
        last_active_tenant_id=TENANT_ID,
    )

    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=existing_user))

    user = await get_or_create_user(TEST_CLAIMS, session, verifier)

    assert user.id == USER_ID
    session.add.assert_not_called()
    verifier.get_user.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_clerk_id_when_no_github():
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))
    verifier = make_mock_verifier(github_username=None, github_account_id=None)

    claims = {"sub": "user_nogh123", "email": "ngh@example.com"}
    await get_or_create_user(claims, session, verifier)

    added = [call.args[0] for call in session.add.call_args_list]
    tenant_obj = next(o for o in added if isinstance(o, Tenant))
    assert tenant_obj.name == "user_nogh123"
    assert tenant_obj.slug is None


@pytest.mark.asyncio
async def test_handles_missing_verifier():
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    claims = {"sub": "user_minimal"}
    await get_or_create_user(claims, session, verifier=None)

    added = [call.args[0] for call in session.add.call_args_list]
    user_obj = next(o for o in added if isinstance(o, User))
    assert user_obj.github_account_id is None
    assert user_obj.github_username is None
    assert user_obj.email is None


@pytest.mark.asyncio
async def test_backfills_github_data_on_subsequent_login_when_missing():
    session = make_mock_session()
    verifier = make_mock_verifier()

    existing_user = User(
        id=USER_ID,
        clerk_user_id="user_clerk123",
        email="dev@example.com",
        github_username=None,
        github_account_id=None,
        last_active_tenant_id=TENANT_ID,
    )

    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=existing_user))

    user = await get_or_create_user(TEST_CLAIMS, session, verifier)

    assert user.github_username == "devuser"
    assert user.github_account_id == 98765
    verifier.get_user.assert_called_once_with("user_clerk123")
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_clerk_api_failure_during_create_is_handled():
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    verifier = AsyncMock()
    verifier.get_user = AsyncMock(side_effect=Exception("Clerk API unavailable"))

    user = await get_or_create_user(TEST_CLAIMS, session, verifier)

    assert user.github_username is None
    assert user.github_account_id is None
    assert user.email == "dev@example.com"
