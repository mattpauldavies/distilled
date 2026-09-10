import pytest

from app.services.ingest_pr_service import handle_pull_request_event
from app.services.webhook_service import SKIPPED
from tests.conftest import make_repo, mock_insert_result, mock_result


def _pull_request_payload(action="closed", merged=True, repo_github_id=111, draft=False):
    return {
        "action": action,
        "pull_request": {
            "id": 99001,
            "merged": merged,
            "draft": draft,
            "number": 7,
            "title": "My PR",
            "merge_commit_sha": "abc1230000",
            "body": "desc",
            "head": {"ref": "feature-branch", "sha": "def456"},
            "base": {"ref": "main"},
            "merged_at": "2025-01-15T11:00:00Z" if merged else None,
            "created_at": "2025-01-10T09:00:00Z",
            "user": {"login": "dev"},
            "html_url": "https://github.com/org/repo/pull/7",
        },
        "repository": {
            "id": repo_github_id,
            "full_name": "org/repo",
        },
        "installation": {"id": 42},
    }


# --- handle_pull_request_event ---


@pytest.mark.asyncio
async def test_skips_unhandled_action(mock_session):
    payload = _pull_request_payload(action="labeled")
    result = await handle_pull_request_event(payload, mock_session)
    mock_session.execute.assert_not_called()
    assert result == SKIPPED


@pytest.mark.asyncio
async def test_unknown_repo_returns_skipped(mock_session):
    payload = _pull_request_payload()
    mock_session.execute.side_effect = [mock_result(rows=[])]

    result = await handle_pull_request_event(payload, mock_session)

    assert result == SKIPPED


@pytest.mark.asyncio
async def test_opened_pr_inserts(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="opened", merged=False)

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_opened_draft_pr_inserts(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="opened", merged=False, draft=True)

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_closed_without_merge_sets_closed_at(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="closed", merged=False)

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_converted_to_draft(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="converted_to_draft", merged=False)

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_ready_for_review(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="ready_for_review", merged=False)

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_reopened_pr(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload(action="reopened", merged=False)

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_inserts_merged_pr(mock_session):
    repo = make_repo(github_id=111)
    payload = _pull_request_payload()

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)

    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_pull_request_event_stores_opened_at(mock_session):
    """Webhook handler should parse opened_at from pr_data.created_at."""

    repo = make_repo(github_id=111)
    payload = _pull_request_payload()
    payload["pull_request"]["created_at"] = "2025-01-10T09:00:00Z"

    mock_session.execute.side_effect = [
        mock_result(rows=[repo]),
        mock_insert_result(1),
    ]

    await handle_pull_request_event(payload, mock_session)

    insert_call = mock_session.execute.call_args_list[1]
    stmt = insert_call.args[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    assert "opened_at" in sql
    assert "2025-01-10" in sql


@pytest.mark.asyncio
async def test_same_repo_in_two_workspaces_upserts_into_both(mock_session):
    """A GitHub repo tracked by two workspaces gets one PullRequest row per workspace."""
    import uuid as _uuid

    tenant_b = _uuid.uuid4()
    repo_a = make_repo(github_id=222)
    repo_b = make_repo(github_id=222, tenant_id=tenant_b)
    payload = _pull_request_payload(action="opened", merged=False, repo_github_id=222)

    mock_session.execute.side_effect = [
        mock_result(rows=[repo_a, repo_b]),
        mock_insert_result(1),  # upsert into workspace A
        mock_insert_result(1),  # upsert into workspace B
    ]

    result = await handle_pull_request_event(payload, mock_session)

    assert result is None
    assert mock_session.execute.call_count == 3
