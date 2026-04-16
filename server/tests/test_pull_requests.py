import uuid

import pytest

from tests.conftest import REPO_ID, make_deployment, make_pr, mock_count_result, mock_result


@pytest.mark.asyncio
async def test_list_pull_requests(client, mock_session):
    pr = make_pr()
    mock_session.execute.side_effect = [
        mock_count_result(1),
        mock_result(rows=[pr]),
    ]

    response = await client.get(f"/pull-requests?repo_id={REPO_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(pr.id)
    assert data["items"][0]["title"] == pr.title
    assert data["items"][0]["number"] == pr.number


@pytest.mark.asyncio
async def test_list_pull_requests_empty(client, mock_session):
    mock_session.execute.side_effect = [
        mock_count_result(0),
        mock_result(rows=[]),
    ]

    response = await client.get(f"/pull-requests?repo_id={REPO_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_get_pull_request_with_deployment(client, mock_session):
    pr = make_pr()
    deployment = make_deployment()
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=pr),
        mock_result(scalar_or_none=deployment),
    ]

    response = await client.get(f"/pull-requests/{pr.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(pr.id)
    assert data["deployment"] is not None
    assert data["deployment"]["id"] == str(deployment.id)
    assert data["deployment"]["environment_name"] == deployment.environment_name
    assert data["deployment"]["commit_sha"] == deployment.commit_sha


@pytest.mark.asyncio
async def test_get_pull_request_without_deployment(client, mock_session):
    pr = make_pr()
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=pr),
        mock_result(scalar_or_none=None),
    ]

    response = await client.get(f"/pull-requests/{pr.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(pr.id)
    assert data["deployment"] is None


@pytest.mark.asyncio
async def test_get_pull_request_not_found(client, mock_session):
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=None),
    ]

    response = await client.get(f"/pull-requests/{uuid.uuid4()}")

    assert response.status_code == 404
