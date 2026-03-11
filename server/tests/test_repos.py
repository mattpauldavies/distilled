import pytest
from tests.conftest import mock_result, mock_count_result, make_repo, make_environment


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
async def test_list_environments(client, mock_session):
    env1 = make_environment()
    env2 = make_environment(name="staging")
    mock_session.execute.side_effect = [
        mock_result(rows=[env1, env2]),
    ]

    repo_id = str(make_repo().id)
    response = await client.get(f"/api/repos/{repo_id}/environments")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == str(env1.id)
    assert data[1]["id"] == str(env2.id)


@pytest.mark.asyncio
async def test_update_environment(client, mock_session):
    env = make_environment(is_production=False)
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=env),
    ]

    def set_is_production(obj):
        pass  # env.is_production will be set by the route before refresh

    response = await client.patch(
        f"/api/repos/{env.repo_id}/environments/{env.id}",
        json={"is_production": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_production"] is True


@pytest.mark.asyncio
async def test_update_environment_not_found(client, mock_session):
    import uuid

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=None),
    ]

    response = await client.patch(
        f"/api/repos/{uuid.uuid4()}/environments/{uuid.uuid4()}",
        json={"is_production": True},
    )

    assert response.status_code == 404
