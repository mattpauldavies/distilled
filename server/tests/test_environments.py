import uuid

import pytest
from tests.conftest import mock_result, make_repo, make_environment


@pytest.mark.asyncio
async def test_list_environments(client, mock_session):
    env1 = make_environment()
    env2 = make_environment(name="staging")
    mock_session.execute.side_effect = [
        mock_result(rows=[env1, env2]),
    ]

    response = await client.get("/api/environments")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == str(env1.id)
    assert data[1]["id"] == str(env2.id)


@pytest.mark.asyncio
async def test_list_environments_by_repo(client, mock_session):
    env1 = make_environment()
    mock_session.execute.side_effect = [
        mock_result(rows=[env1]),
    ]

    repo_id = str(make_repo().id)
    response = await client.get(f"/api/environments?repo_id={repo_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(env1.id)


@pytest.mark.asyncio
async def test_update_environment(client, mock_session):
    env = make_environment(is_production=False)
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=env),
    ]

    response = await client.patch(
        f"/api/environments/{env.id}",
        json={"is_production": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_production"] is True


@pytest.mark.asyncio
async def test_update_environment_not_found(client, mock_session):
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=None),
    ]

    response = await client.patch(
        f"/api/environments/{uuid.uuid4()}",
        json={"is_production": True},
    )

    assert response.status_code == 404
