from datetime import timedelta

import pytest

from app.services.attribution_service import attribute_prs_to_deployment
from tests.conftest import (
    NOW,
    make_deployment,
    make_pr,
    make_repo,
    mock_insert_result,
    mock_result,
)


@pytest.mark.asyncio
async def test_with_previous_deployment(mock_session):
    repo = make_repo()
    deployment = make_deployment(repo_id=repo.id)
    prev_deployment = make_deployment(repo_id=repo.id, deployed_at=NOW - timedelta(days=1))
    pr1 = make_pr(repo_id=repo.id)
    pr2 = make_pr(repo_id=repo.id)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=prev_deployment),
        mock_result(rows=[pr1, pr2]),
        mock_insert_result(1),
        mock_insert_result(1),
    ]

    await attribute_prs_to_deployment(deployment, repo, mock_session)

    assert mock_session.execute.call_count == 4


@pytest.mark.asyncio
async def test_without_previous_deployment(mock_session):
    repo = make_repo()
    deployment = make_deployment(repo_id=repo.id)
    pr = make_pr(repo_id=repo.id)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=None),
        mock_result(rows=[pr]),
        mock_insert_result(1),
    ]

    await attribute_prs_to_deployment(deployment, repo, mock_session)

    assert mock_session.execute.call_count == 3


@pytest.mark.asyncio
async def test_no_prs_in_window(mock_session):
    repo = make_repo()
    deployment = make_deployment(repo_id=repo.id)

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=None),
        mock_result(rows=[]),
    ]

    await attribute_prs_to_deployment(deployment, repo, mock_session)

    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_multiple_prs_attributed(mock_session):
    repo = make_repo()
    deployment = make_deployment(repo_id=repo.id)
    prev_deployment = make_deployment(repo_id=repo.id, deployed_at=NOW - timedelta(days=2))
    prs = [make_pr(repo_id=repo.id) for _ in range(3)]

    mock_session.execute.side_effect = [
        mock_result(scalar_or_none=prev_deployment),
        mock_result(rows=prs),
        mock_insert_result(1),
        mock_insert_result(1),
        mock_insert_result(1),
    ]

    await attribute_prs_to_deployment(deployment, repo, mock_session)

    assert mock_session.execute.call_count == 5
