import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import require_user
from app.db import get_session
from app.main import create_app
from app.models.user import User

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def make_user() -> User:
    return User(
        id=USER_ID,
        clerk_user_id="user_test123",
        email="dev@example.com",
        github_username="devuser",
        github_account_id=98765,
        last_active_tenant_id=None,
    )


@pytest.fixture
def user():
    return make_user()


@pytest.fixture
def client(mock_session, user):
    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: user

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_create_workspace_returns_created_workspace(client, user, mock_session):
    response = await client.post("/workspaces", json={"name": "Acme Engineering"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Engineering"
    assert body["role"] == "owner"
    assert uuid.UUID(body["id"])
    # creating a workspace makes it the active one
    assert user.last_active_tenant_id == uuid.UUID(body["id"])


@pytest.mark.asyncio
async def test_create_workspace_rejects_empty_name(client):
    response = await client.post("/workspaces", json={"name": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_workspace_rejects_whitespace_name(client):
    response = await client.post("/workspaces", json={"name": "   "})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_workspace_requires_auth(mock_session):
    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    client = AsyncClient(transport=transport, base_url="http://test")

    response = await client.post("/workspaces", json={"name": "Acme"})
    assert response.status_code == 401
