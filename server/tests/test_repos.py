import pytest

from tests.conftest import make_repo, mock_count_result, mock_result


@pytest.mark.asyncio
async def test_list_repos(client, mock_session):
    repo = make_repo()
    mock_session.execute.side_effect = [
        mock_count_result(1),
        mock_result(rows=[repo]),
    ]

    response = await client.get("/api/repos")

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

    response = await client.get("/api/repos")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


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
    # deliberately do NOT override require_api_key

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        resp = await client.get("/api/repos")

    assert resp.status_code == 403  # HTTPBearer returns 403 for missing Authorization header
