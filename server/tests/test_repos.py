import pytest
from tests.conftest import mock_result, mock_count_result, make_repo


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
