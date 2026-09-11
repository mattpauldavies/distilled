import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ingest_deployment_service import handle_deployment_status_event
from app.services.webhook_service import SKIPPED
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
    result = await handle_deployment_status_event(payload, mock_session)
    mock_session.execute.assert_not_called()
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_skips_unknown_repo(mock_session):
    payload = _deployment_status_payload()
    mock_session.execute.side_effect = [
        mock_result(rows=[]),
    ]

    result = await handle_deployment_status_event(payload, mock_session)

    assert mock_session.execute.call_count == 1
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_skips_non_production_env(mock_session, caplog):
    repo = make_repo(github_id=111)
    env = make_environment(repo_id=repo.id, name="staging", is_production=False)
    payload = _deployment_status_payload(env_name="staging")

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_result(scalar_or_none=env),
    ]

    with caplog.at_level(logging.DEBUG, logger="app.services.ingest_deployment_service"):
        result = await handle_deployment_status_event(payload, mock_session)

    assert mock_session.execute.call_count == 2
    assert result == SKIPPED
    assert any("environment_not_production" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_undiscovered_env_warns_rather_than_claiming_non_production(mock_session, caplog):
    """An environment with no row was never discovered — usually because listing the
    repo's environments was refused (see environments_forbidden). Calling that
    "non-prod" hides the real cause of a repo with no deployment metrics."""
    repo = make_repo(github_id=111)
    payload = _deployment_status_payload()

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_result(scalar_or_none=None),
    ]

    with caplog.at_level(logging.DEBUG, logger="app.services.ingest_deployment_service"):
        result = await handle_deployment_status_event(payload, mock_session)

    assert result == SKIPPED
    record = next(r for r in caplog.records if "environment_unknown" in r.getMessage())
    assert record.levelno == logging.WARNING
    assert "production" in record.getMessage()  # the environment name from the payload
    assert "non-prod" not in record.getMessage()


@pytest.mark.asyncio
@patch("app.services.ingest_deployment_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_processes_successful_deployment(mock_attribute, mock_session):
    repo = make_repo(github_id=111)
    env = make_environment(repo_id=repo.id)
    deployment = make_deployment(repo_id=repo.id)
    payload = _deployment_status_payload()

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_result(scalar_or_none=env),
        mock_insert_result(1),
        mock_result(scalar=deployment),
    ]

    await handle_deployment_status_event(payload, mock_session)

    assert mock_session.execute.call_count == 4
    mock_attribute.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.ingest_deployment_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_same_repo_in_two_workspaces_ingests_into_both(mock_attribute, mock_session):
    """A GitHub repo tracked by two workspaces produces one deployment event per workspace."""
    import uuid as _uuid

    tenant_b = _uuid.uuid4()
    repo_a = make_repo(github_id=111)
    repo_b = make_repo(github_id=111, tenant_id=tenant_b)
    env_a = make_environment(repo_id=repo_a.id)
    env_b = make_environment(repo_id=repo_b.id, tenant_id=tenant_b)
    dep_a = make_deployment(repo_id=repo_a.id)
    dep_b = make_deployment(repo_id=repo_b.id, tenant_id=tenant_b)
    payload = _deployment_status_payload()

    mock_session.execute.side_effect = [
        mock_result(rows=[repo_a, repo_b]),
        mock_result(scalar_or_none=env_a),
        mock_insert_result(1),
        mock_result(scalar=dep_a),
        mock_result(scalar_or_none=env_b),
        mock_insert_result(1),
        mock_result(scalar=dep_b),
    ]

    result = await handle_deployment_status_event(payload, mock_session)

    assert result is None
    assert mock_session.execute.call_count == 7
    assert mock_attribute.await_count == 2


@pytest.mark.asyncio
@patch("app.services.ingest_deployment_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_fan_out_skips_workspace_without_production_env(mock_attribute, mock_session):
    """One workspace marks the environment production, the other doesn't — only the
    first ingests, and the event still counts as handled."""
    import uuid as _uuid

    tenant_b = _uuid.uuid4()
    repo_a = make_repo(github_id=111)
    repo_b = make_repo(github_id=111, tenant_id=tenant_b)
    env_a = make_environment(repo_id=repo_a.id)
    dep_a = make_deployment(repo_id=repo_a.id)
    payload = _deployment_status_payload()

    mock_session.execute.side_effect = [
        mock_result(rows=[repo_a, repo_b]),
        mock_result(scalar_or_none=env_a),
        mock_insert_result(1),
        mock_result(scalar=dep_a),
        mock_result(scalar_or_none=None),  # workspace B: env not production
    ]

    result = await handle_deployment_status_event(payload, mock_session)

    assert result is None
    assert mock_attribute.await_count == 1
