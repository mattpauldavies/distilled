import uuid

import pytest

from tests.conftest import REPO_ID, make_deployment, make_pr, mock_count_result, mock_result


@pytest.mark.asyncio
async def test_list_deployments(client, mock_session):
    deployment = make_deployment()
    mock_session.execute.side_effect = [
        mock_count_result(1),
        mock_result(rows=[deployment]),
    ]

    response = await client.get(f"/deployments?repo_id={REPO_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(deployment.id)
    assert data["items"][0]["commit_sha"] == deployment.commit_sha
    assert data["items"][0]["environment_name"] == deployment.environment_name


@pytest.mark.asyncio
async def test_list_deployments_empty(client, mock_session):
    mock_session.execute.side_effect = [
        mock_count_result(0),
        mock_result(rows=[]),
    ]

    response = await client.get(f"/deployments?repo_id={REPO_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_get_deployment(client, mock_session):
    deployment = make_deployment()
    pr = make_pr()
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=deployment),
        mock_result(rows=[pr]),
    ]

    response = await client.get(f"/deployments/{deployment.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(deployment.id)
    assert len(data["attributed_prs"]) == 1
    assert data["attributed_prs"][0]["id"] == str(pr.id)
    assert data["attributed_prs"][0]["title"] == pr.title


@pytest.mark.asyncio
async def test_get_deployment_not_found(client, mock_session):
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=None),
    ]

    response = await client.get(f"/deployments/{uuid.uuid4()}")

    assert response.status_code == 404
