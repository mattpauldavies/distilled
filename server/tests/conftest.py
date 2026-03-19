import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_session
from app.main import create_app
from app.middleware.repo import get_verified_repo
from app.middleware.tenant import get_tenant_id
from app.models.deployment_event import ProductionDeploymentEvent
from app.models.environment import Environment
from app.models.github_installation import GitHubInstallation
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.tenant import Tenant

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
REPO_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def tenant_id():
    return TENANT_ID


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


def mock_result(rows=None, scalar=None, scalar_or_none=None):
    """Build a mock Result that supports common SQLAlchemy access patterns."""
    result = MagicMock()
    if rows is not None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = rows
        result.scalars.return_value = scalars_mock
    if scalar is not None:
        result.scalar_one.return_value = scalar
    if scalar_or_none is not None:
        result.scalar_one_or_none.return_value = scalar_or_none
    else:
        result.scalar_one_or_none.return_value = None
    return result


def mock_count_result(count: int):
    """Build a mock Result for COUNT queries."""
    result = MagicMock()
    result.scalar_one.return_value = count
    return result


def mock_insert_result(rowcount: int = 1):
    """Build a mock Result for INSERT statements."""
    result = MagicMock()
    result.rowcount = rowcount
    return result


@pytest.fixture
def client(mock_session, tenant_id):
    app = create_app()

    async def override_session():
        yield mock_session

    repo = make_repo(id=REPO_ID)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_tenant_id] = lambda: tenant_id
    app.dependency_overrides[get_verified_repo] = lambda: repo

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


# --- Model factories ---


def make_tenant(**overrides):
    defaults = dict(
        id=TENANT_ID,
        name="dev",
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return _make_model(Tenant, defaults)


def make_repo(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        installation_id=uuid.uuid4(),
        github_id=12345,
        full_name="org/repo",
        default_branch="main",
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return _make_model(Repository, defaults)


def make_environment(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        repo_id=uuid.uuid4(),
        name="production",
        is_production=True,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return _make_model(Environment, defaults)


def make_pr(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        repo_id=uuid.uuid4(),
        github_id=99999,
        number=1,
        title="Fix bug",
        base_ref="main",
        merged_at=NOW,
        opened_at=NOW,
        merge_commit_sha="abc123" + "0" * 34,
        head_sha="def456" + "0" * 34,
        author_login="dev",
        html_url="https://github.com/org/repo/pull/1",
        created_at=NOW,
        updated_at=NOW,
        is_draft=False,
        closed_at=None,
    )
    defaults.update(overrides)
    return _make_model(PullRequest, defaults)


def make_deployment(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        repo_id=uuid.uuid4(),
        environment_name="production",
        deployment_id=1001,
        commit_sha="aaa111" + "0" * 34,
        ref="main",
        started_at=NOW,
        completed_at=NOW,
        deployed_at=NOW,
        html_url="https://github.com/org/repo/deployments/1001",
        created_at=NOW,
    )
    defaults.update(overrides)
    return _make_model(ProductionDeploymentEvent, defaults)


def make_installation(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        installation_id=100,
        account_login="org",
        account_type="organization",
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return _make_model(GitHubInstallation, defaults)


def _make_model(model_class, attrs):
    """Create a model instance without DB using the normal constructor."""
    return model_class(**attrs)
