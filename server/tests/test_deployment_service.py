from unittest.mock import AsyncMock, patch

import pytest

from app.services.deployment_service import handle_deployment_status_event
from tests.conftest import (
    make_deployment,
    make_environment,
    make_repo,
    mock_insert_result,
    mock_result,
)


def _deployment_status_payload(state="success", repo_github_id=111, env_name="production"):
    return {
        "deployment_status": {
            "state": state,
            "created_at": "2025-01-15T12:00:00Z",
            "updated_at": "2025-01-15T12:05:00Z",
        },
        "deployment": {
            "id": 5001,
            "environment": env_name,
            "sha": "abc123",
            "ref": "main",
            "created_at": "2025-01-15T11:55:00Z",
        },
        "repository": {
            "id": repo_github_id,
            "full_name": "org/repo",
        },
        "installation": {"id": 42},
    }


# --- handle_deployment_status_event ---


@pytest.mark.asyncio
async def test_skips_non_success(mock_session):
    payload = _deployment_status_payload(state="failure")
    await handle_deployment_status_event(payload, mock_session)
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_skips_unknown_repo(mock_session):
    payload = _deployment_status_payload()
    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=None),
    ]

    await handle_deployment_status_event(payload, mock_session)

    assert mock_session.execute.call_count == 1


@pytest.mark.asyncio
async def test_skips_non_production_env(mock_session):
    repo = make_repo(github_id=111)
    payload = _deployment_status_payload()

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_result(scalar_or_none=None),
    ]

    await handle_deployment_status_event(payload, mock_session)

    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
@patch("app.services.deployment_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_processes_successful_deployment(mock_attribute, mock_session):
    repo = make_repo(github_id=111)
    env = make_environment(repo_id=repo.id)
    deployment = make_deployment(repo_id=repo.id)
    payload = _deployment_status_payload()

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_result(scalar_or_none=env),
        mock_insert_result(1),
        mock_result(scalar=deployment),
    ]

    await handle_deployment_status_event(payload, mock_session)

    assert mock_session.execute.call_count == 4
    mock_attribute.assert_awaited_once()
