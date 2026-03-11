import pytest
from unittest.mock import AsyncMock, patch

from tests.conftest import mock_result, mock_insert_result, make_repo, make_deployment, make_environment, TENANT_ID, NOW
from app.services.deployment_service import handle_deployment_status_event, handle_pull_request_event


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


def _pull_request_payload(action="closed", merged=True, repo_github_id=111):
    return {
        "action": action,
        "pull_request": {
            "id": 99001,
            "merged": merged,
            "number": 7,
            "title": "My PR",
            "merge_commit_sha": "abc1230000",
            "body": "desc",
            "head": {"ref": "feature-branch", "sha": "def456"},
            "base": {"ref": "main"},
            "merged_at": "2025-01-15T11:00:00Z",
            "user": {"login": "dev"},
            "html_url": "https://github.com/org/repo/pull/7",
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


# --- handle_pull_request_event ---


@pytest.mark.asyncio
async def test_skips_non_closed(mock_session):
    payload = _pull_request_payload(action="opened")
    await handle_pull_request_event(payload, mock_session)
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_skips_non_merged(mock_session):
    payload = _pull_request_payload(action="closed", merged=False)
    await handle_pull_request_event(payload, mock_session)
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_inserts_merged_pr(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload()

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)

    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_pull_request_event_stores_opened_at(mock_session):
    """Webhook handler should parse opened_at from pr_data.created_at."""
    from datetime import datetime, timezone

    repo = make_repo(github_id=111)
    payload = _pull_request_payload()
    payload["pull_request"]["created_at"] = "2025-01-10T09:00:00Z"

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=repo),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)

    insert_call = mock_session.execute.call_args_list[1]
    stmt = insert_call.args[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    assert "opened_at" in sql
    assert "2025-01-10" in sql
