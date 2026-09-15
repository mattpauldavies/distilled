import logging
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.services.ingest_release_service import RELEASE_ENVIRONMENT_NAME, handle_release_event
from app.services.webhook_service import SKIPPED
from tests.conftest import make_deployment, make_repo, mock_insert_result, mock_result


def _release_payload(action="published", repo_github_id=111, **release_overrides):
    release = {
        "id": 7001,
        "tag_name": "v2.4.0",
        "target_commitish": "main",
        "draft": False,
        "prerelease": False,
        "created_at": "2025-01-15T11:55:00Z",
        "published_at": "2025-01-15T12:00:00Z",
        "html_url": "https://github.com/org/repo/releases/tag/v2.4.0",
    }
    release.update(release_overrides)
    return {
        "action": action,
        "release": release,
        "repository": {"id": repo_github_id, "full_name": "org/repo"},
        "installation": {"id": 42},
    }


def _insert_params(stmt):
    return stmt.compile(dialect=postgresql.dialect()).params


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["created", "edited", "deleted", "prereleased"])
async def test_skips_actions_other_than_published(mock_session, action):
    """`created` fires when a draft is saved and never fires again on publication."""
    result = await handle_release_event(_release_payload(action=action), mock_session)

    mock_session.execute.assert_not_called()
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_skips_draft(mock_session):
    result = await handle_release_event(_release_payload(draft=True), mock_session)

    mock_session.execute.assert_not_called()
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_skips_prerelease(mock_session):
    result = await handle_release_event(_release_payload(prerelease=True), mock_session)

    mock_session.execute.assert_not_called()
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_skips_unknown_repo(mock_session):
    mock_session.execute.side_effect = [mock_result(rows=[])]

    result = await handle_release_event(_release_payload(), mock_session)

    assert mock_session.execute.call_count == 1
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_skips_repo_tracking_deployments(mock_session, caplog):
    repo = make_repo(github_id=111, deployment_source="deployment")
    mock_session.execute.side_effect = [mock_result(rows=[repo])]

    with caplog.at_level(logging.DEBUG, logger="app.services.ingest_release_service"):
        result = await handle_release_event(_release_payload(), mock_session)

    assert mock_session.execute.call_count == 1
    assert result == SKIPPED
    assert any("repo_not_tracking_releases" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
@patch("app.services.ingest_release_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_records_published_release(mock_attribute, mock_session):
    repo = make_repo(github_id=111, deployment_source="release")
    deployment = make_deployment(repo_id=repo.id, source="release")
    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
        mock_result(scalar=deployment),
    ]

    result = await handle_release_event(_release_payload(), mock_session)

    assert result is None
    params = _insert_params(mock_session.execute.call_args_list[1][0][0])
    assert params["deployment_id"] == 7001
    assert params["environment_name"] == RELEASE_ENVIRONMENT_NAME
    assert params["source"] == "release"
    assert params["repo_id"] == repo.id
    assert params["tenant_id"] == repo.tenant_id
    assert params["html_url"] == "https://github.com/org/repo/releases/tag/v2.4.0"
    mock_attribute.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.ingest_release_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_deployed_at_is_publication_time(mock_attribute, mock_session):
    repo = make_repo(github_id=111, deployment_source="release")
    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
        mock_result(scalar=make_deployment(repo_id=repo.id, source="release")),
    ]

    await handle_release_event(_release_payload(), mock_session)

    params = _insert_params(mock_session.execute.call_args_list[1][0][0])
    assert params["deployed_at"].isoformat() == "2025-01-15T12:00:00+00:00"
    assert params["completed_at"] == params["deployed_at"]
    assert params["started_at"].isoformat() == "2025-01-15T11:55:00+00:00"


@pytest.mark.asyncio
@patch("app.services.ingest_release_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_falls_back_to_created_at_without_published_at(mock_attribute, mock_session):
    repo = make_repo(github_id=111, deployment_source="release")
    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
        mock_result(scalar=make_deployment(repo_id=repo.id, source="release")),
    ]

    await handle_release_event(_release_payload(published_at=None), mock_session)

    params = _insert_params(mock_session.execute.call_args_list[1][0][0])
    assert params["deployed_at"].isoformat() == "2025-01-15T11:55:00+00:00"


@pytest.mark.asyncio
@patch("app.services.ingest_release_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_rejects_html_url_outside_github(mock_attribute, mock_session):
    repo = make_repo(github_id=111, deployment_source="release")
    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
        mock_result(scalar=make_deployment(repo_id=repo.id, source="release")),
    ]

    await handle_release_event(_release_payload(html_url="https://evil.example.com/releases/v1"), mock_session)

    params = _insert_params(mock_session.execute.call_args_list[1][0][0])
    assert params["html_url"] == ""


@pytest.mark.asyncio
@patch("app.services.ingest_release_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_redelivered_release_is_not_attributed_twice(mock_attribute, mock_session):
    repo = make_repo(github_id=111, deployment_source="release")
    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(0),
    ]

    result = await handle_release_event(_release_payload(), mock_session)

    assert result is None
    mock_attribute.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.services.ingest_release_service.attribute_prs_to_deployment", new_callable=AsyncMock)
async def test_fan_out_records_only_release_tracked_workspaces(mock_attribute, mock_session):
    """Two workspaces track the repo in different modes; only one counts the release."""
    repo_deployments = make_repo(github_id=111, deployment_source="deployment")
    repo_releases = make_repo(github_id=111, tenant_id=uuid.uuid4(), deployment_source="release")
    mock_session.execute.side_effect = [
        mock_result(rows=[repo_deployments, repo_releases]),
        mock_insert_result(1),
        mock_result(scalar=make_deployment(repo_id=repo_releases.id, source="release")),
    ]

    result = await handle_release_event(_release_payload(), mock_session)

    assert result is None
    assert mock_session.execute.call_count == 3
    params = _insert_params(mock_session.execute.call_args_list[1][0][0])
    assert params["repo_id"] == repo_releases.id
    mock_attribute.assert_awaited_once()
