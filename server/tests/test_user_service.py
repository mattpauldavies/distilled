import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.tenant import Tenant
from app.models.user import User
from app.services.user_service import get_or_create_user_and_tenant


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

# Claims now only carry sub and email (external_accounts come from Clerk API)
TEST_CLAIMS = {
    "sub": "user_clerk123",
    "email": "dev@example.com",
}


@pytest.mark.asyncio
async def test_first_call_creates_tenant_and_user():
    """First call for a new clerk_user_id creates Tenant and User with GitHub data from API."""
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))
    verifier = make_mock_verifier()

    user, tenant = await get_or_create_user_and_tenant(TEST_CLAIMS, session, verifier)

    assert session.add.call_count == 2
    assert session.flush.call_count == 2
    session.commit.assert_called_once()

    added_objects = [call.args[0] for call in session.add.call_args_list]
    tenant_obj = next(obj for obj in added_objects if isinstance(obj, Tenant))
    user_obj = next(obj for obj in added_objects if isinstance(obj, User))

    assert tenant_obj.name == "devuser"
    assert tenant_obj.slug == "devuser"
    assert user_obj.clerk_user_id == "user_clerk123"
    assert user_obj.email == "dev@example.com"
    assert user_obj.github_username == "devuser"
    assert user_obj.github_account_id == 98765

    verifier.get_user.assert_called_once_with("user_clerk123")


@pytest.mark.asyncio
async def test_second_call_returns_existing_records():
    """Second call for the same clerk_user_id returns existing records without calling the API."""
    session = make_mock_session()
    verifier = make_mock_verifier()

    existing_user = User(
        id=USER_ID,
        clerk_user_id="user_clerk123",
        email="dev@example.com",
        github_username="devuser",
        github_account_id=98765,
        tenant_id=TENANT_ID,
    )
    existing_tenant = Tenant(id=TENANT_ID, name="devuser", slug="devuser")

    session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=existing_user),
            mock_result(scalar_or_none=existing_tenant),
        ]
    )

    user, tenant = await get_or_create_user_and_tenant(TEST_CLAIMS, session, verifier)

    assert user.id == USER_ID
    assert tenant.id == TENANT_ID
    session.add.assert_not_called()
    # Clerk API should not be called for existing users
    verifier.get_user.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_clerk_id_when_no_github():
    """Tenant name falls back to clerk_user_id when GitHub account is absent from API."""
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))
    verifier = make_mock_verifier(github_username=None, github_account_id=None)

    claims = {"sub": "user_nogh123", "email": "ngh@example.com"}
    user, tenant = await get_or_create_user_and_tenant(claims, session, verifier)

    added_objects = [call.args[0] for call in session.add.call_args_list]
    tenant_obj = next(obj for obj in added_objects if isinstance(obj, Tenant))
    assert tenant_obj.name == "user_nogh123"
    assert tenant_obj.slug is None


@pytest.mark.asyncio
async def test_handles_missing_verifier():
    """Without a verifier, GitHub fields are null but user is still created."""
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    claims = {"sub": "user_minimal"}
    user, tenant = await get_or_create_user_and_tenant(claims, session, verifier=None)

    added_objects = [call.args[0] for call in session.add.call_args_list]
    user_obj = next(obj for obj in added_objects if isinstance(obj, User))
    assert user_obj.github_account_id is None
    assert user_obj.github_username is None
    assert user_obj.email is None


@pytest.mark.asyncio
async def test_backfills_github_data_on_subsequent_login():
    """If github_account_id is missing on an existing user, it is filled in on next login."""
    session = make_mock_session()
    verifier = make_mock_verifier()

    existing_user = User(
        id=USER_ID,
        clerk_user_id="user_clerk123",
        email="dev@example.com",
        github_username=None,
        github_account_id=None,
        tenant_id=TENANT_ID,
    )
    existing_tenant = Tenant(id=TENANT_ID, name="user_clerk123", slug=None)

    session.execute = AsyncMock(
        side_effect=[
            mock_result(scalar_or_none=existing_user),
            mock_result(scalar_or_none=existing_tenant),
        ]
    )

    user, tenant = await get_or_create_user_and_tenant(TEST_CLAIMS, session, verifier)

    assert user.github_username == "devuser"
    assert user.github_account_id == 98765
    assert tenant.slug == "devuser"
    verifier.get_user.assert_called_once_with("user_clerk123")
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_clerk_api_failure_is_handled_gracefully():
    """If the Clerk API call fails, user is still created with null GitHub fields."""
    session = make_mock_session()
    session.execute = AsyncMock(return_value=mock_result(scalar_or_none=None))

    verifier = AsyncMock()
    verifier.get_user = AsyncMock(side_effect=Exception("Clerk API unavailable"))

    user, tenant = await get_or_create_user_and_tenant(TEST_CLAIMS, session, verifier)

    added_objects = [call.args[0] for call in session.add.call_args_list]
    user_obj = next(obj for obj in added_objects if isinstance(obj, User))
    assert user_obj.github_username is None
    assert user_obj.github_account_id is None
    # Email from JWT is still stored
    assert user_obj.email == "dev@example.com"
