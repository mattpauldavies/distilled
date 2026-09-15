import uuid

import pytest

from tests.conftest import make_repo, mock_count_result, mock_result


@pytest.mark.asyncio
async def test_list_repos(client, mock_session):
    repo = make_repo()
    mock_session.execute.side_effect = [
        mock_count_result(1),
        mock_result(rows=[repo]),
    ]

    response = await client.get("/repos")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(repo.id)
    assert data["items"][0]["full_name"] == repo.full_name
    assert data["items"][0]["default_branch"] == repo.default_branch


@pytest.mark.asyncio
async def test_list_repos_empty(client, mock_session):
    mock_session.execute.side_effect = [
        mock_count_result(0),
        mock_result(rows=[]),
    ]

    response = await client.get("/repos")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_repos_excludes_soft_deleted(client, mock_session):
    """The repo list only returns repos still attached to the installation."""
    mock_session.execute.side_effect = [
        mock_count_result(0),
        mock_result(rows=[]),
    ]

    response = await client.get("/repos")

    assert response.status_code == 200
    select_sql = str(mock_session.execute.call_args_list[1][0][0])
    assert "removed_at IS NULL" in select_sql


@pytest.mark.asyncio
async def test_list_repos_requires_auth(mock_session):
    """Requests without Authorization header must be rejected."""
    from httpx import ASGITransport, AsyncClient

    from app.db import get_session
    from app.main import create_app

    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    # deliberately do NOT override require_auth

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        resp = await client.get("/repos")

    # 503: auth not configured (CLERK_JWKS_URL empty + production env)
    # 401: auth configured but no Authorization header
    assert resp.status_code in (401, 503)


@pytest.mark.asyncio
async def test_list_repos_includes_deployment_source(client, mock_session):
    repo = make_repo(deployment_source="release")
    mock_session.execute.side_effect = [
        mock_count_result(1),
        mock_result(rows=[repo]),
    ]

    response = await client.get("/repos")

    assert response.status_code == 200
    assert response.json()["items"][0]["deployment_source"] == "release"


@pytest.mark.asyncio
async def test_update_repo_sets_deployment_source(client, mock_session):
    repo = make_repo(deployment_source="deployment")
    mock_session.execute.side_effect = [mock_result(scalar_or_none=repo)]

    response = await client.patch(f"/repos/{repo.id}", json={"deployment_source": "release"})

    assert response.status_code == 200
    assert response.json()["deployment_source"] == "release"
    assert repo.deployment_source == "release"
    mock_session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_repo_rejects_unknown_source(client, mock_session):
    repo = make_repo()

    response = await client.patch(f"/repos/{repo.id}", json={"deployment_source": "workflow_run"})

    assert response.status_code == 422
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_repo_unknown_repo_returns_404(client, mock_session):
    mock_session.execute.side_effect = [mock_result(scalar_or_none=None)]

    response = await client.patch(f"/repos/{uuid.uuid4()}", json={"deployment_source": "release"})

    assert response.status_code == 404
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_repo_scoped_to_active_workspace(client, mock_session):
    """The lookup is tenant-scoped so one workspace cannot retarget another's repo."""
    repo = make_repo()
    mock_session.execute.side_effect = [mock_result(scalar_or_none=repo)]

    await client.patch(f"/repos/{repo.id}", json={"deployment_source": "release"})

    select_sql = str(mock_session.execute.call_args_list[0][0][0])
    assert "repositories.tenant_id = " in select_sql


@pytest.mark.asyncio
async def test_update_repo_requires_owner(mock_session):
    """Members cannot change what counts as a deployment."""
    from httpx import ASGITransport, AsyncClient

    from app.auth import CurrentUser, require_auth
    from app.db import get_session
    from app.main import create_app

    app = create_app()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_auth] = lambda: CurrentUser(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="member",
        clerk_user_id="user_member",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as member_client:
        response = await member_client.patch(f"/repos/{uuid.uuid4()}", json={"deployment_source": "release"})

    assert response.status_code == 403
