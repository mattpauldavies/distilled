# RFC 004: Multi-Repo Support

## Summary

Make `repo_id` a required query param on list endpoints for deployments and pull-requests. Add shared repo-ownership validation. Establishes repo-scoped foundation for future metric tables (PRDs 005-007).

## Architectural Rules

- **Prefer RESTful single resource endpoints.** e.g. `/api/deployments` and not `/api/repos/{id}/deployments`
- **Max two resources deep in URL paths.** If nesting is essential `/api/one/{id}/two/{id}` is fine. Three levels is not.
- **List endpoints require `repo_id`.** No cross-repo aggregation.
- **Single resource endpoints are tenant-scoped only.** No redundant repo ownership check on single-resource lookups — tenant scoping already prevents cross-tenant leakage.

## Changes

### 1. `get_verified_repo` dependency

New `app/middleware/repo.py`:

```python
async def get_verified_repo(
    repo_id: uuid.UUID = Query(...),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> Repository:
    # SELECT WHERE id = repo_id AND tenant_id = tenant_id
    # 404 if not found
```

Used by list endpoints to validate repo belongs to tenant before querying.

### 2. Endpoint changes

| Endpoint                      | Before                         | After                                                 |
| ----------------------------- | ------------------------------ | ----------------------------------------------------- |
| `GET /api/deployments`        | `repo_id` optional query param | `repo_id` required, validated via `get_verified_repo` |
| `GET /api/deployments/{id}`   | tenant-scoped                  | Unchanged                                             |
| `GET /api/pull-requests`      | `repo_id` optional query param | `repo_id` required, validated via `get_verified_repo` |
| `GET /api/pull-requests/{id}` | tenant-scoped                  | Unchanged                                             |

### 3. Schema changes

None. Response schemas already include `repo_id`.

### 4. Test changes

All list-endpoint tests must provide `repo_id` query param. Mock `get_verified_repo` dependency.

## Files Changed

| File                          | Action                                   |
| ----------------------------- | ---------------------------------------- |
| `app/middleware/repo.py`      | **New** — `get_verified_repo` dependency |
| `app/routes/deployments.py`   | Make `repo_id` required via dependency   |
| `app/routes/pull_requests.py` | Make `repo_id` required via dependency   |
| `app/main.py`                 | Unchanged                                |
| `app/routes/repos.py`         | Unchanged                                |
| `tests/test_deployments.py`   | Update to provide `repo_id`              |
| `tests/test_pull_requests.py` | Update to provide `repo_id`              |

## Not In Scope

- Computed metric tables (PRD 005)
- Metric endpoints (PRD 006-007)
- Scheduled recompute (PRD 012)
- Client/frontend changes

---

## Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `repo_id` required on list endpoints with tenant-ownership validation.

**Architecture:** New `get_verified_repo` FastAPI dependency validates repo exists + belongs to tenant. List endpoints inject it instead of taking `repo_id` as an optional query param. Detail endpoints unchanged.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest

---

### Task 1: `get_verified_repo` dependency

**Files:**
- Create: `server/app/middleware/repo.py`
- Test: `server/tests/test_repo_middleware.py`

- [ ] **Step 1: Write failing tests for `get_verified_repo`**

```python
# server/tests/test_repo_middleware.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from tests.conftest import TENANT_ID, make_repo, mock_result


@pytest.mark.asyncio
async def test_get_verified_repo_returns_repo():
    from app.middleware.repo import get_verified_repo

    repo = make_repo()
    session = AsyncMock()
    session.execute.return_value = mock_result(scalar_or_none=repo)

    result = await get_verified_repo(
        repo_id=repo.id, tenant_id=TENANT_ID, session=session
    )
    assert result.id == repo.id


@pytest.mark.asyncio
async def test_get_verified_repo_404_when_not_found():
    from app.middleware.repo import get_verified_repo
    from fastapi import HTTPException

    session = AsyncMock()
    session.execute.return_value = mock_result(scalar_or_none=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_verified_repo(
            repo_id=uuid.uuid4(), tenant_id=TENANT_ID, session=session
        )
    assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_repo_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.middleware.repo'`

- [ ] **Step 3: Implement `get_verified_repo`**

```python
# server/app/middleware/repo.py
import uuid

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.middleware.tenant import get_tenant_id
from app.models.repository import Repository


async def get_verified_repo(
    repo_id: uuid.UUID = Query(...),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_session),
) -> Repository:
    result = await session.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.tenant_id == tenant_id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/test_repo_middleware.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add server/app/middleware/repo.py server/tests/test_repo_middleware.py
git commit -m "add get_verified_repo dependency"
```

---

### Task 2: Update deployments list endpoint

**Files:**
- Modify: `server/app/routes/deployments.py`
- Modify: `server/tests/test_deployments.py`
- Modify: `server/tests/conftest.py`

- [ ] **Step 1: Update conftest to add `get_verified_repo` override + `REPO_ID`**

Add to `server/tests/conftest.py`:

```python
# After TENANT_ID line
REPO_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
```

Update the `client` fixture to also override `get_verified_repo`:

```python
from app.middleware.repo import get_verified_repo

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
```

- [ ] **Step 2: Update deployment list tests to pass `repo_id`**

In `server/tests/test_deployments.py`, update imports and list tests:

```python
from tests.conftest import mock_result, mock_count_result, make_deployment, make_pr, REPO_ID
```

Change `test_list_deployments`:
```python
response = await client.get(f"/api/deployments?repo_id={REPO_ID}")
```

Change `test_list_deployments_empty`:
```python
response = await client.get(f"/api/deployments?repo_id={REPO_ID}")
```

- [ ] **Step 3: Run deployment tests to see list tests fail (route still accepts optional)**

Run: `cd server && python -m pytest tests/test_deployments.py -v`
Expected: Tests still pass (repo_id is still optional). This confirms our baseline.

- [ ] **Step 4: Update `deployments.py` to use `get_verified_repo`**

Replace the `list_deployments` function signature and body in `server/app/routes/deployments.py`:

```python
from app.middleware.repo import get_verified_repo
from app.models.repository import Repository
```

Update `list_deployments`:
```python
@router.get("")
async def list_deployments(
    pagination: PaginationParams = Depends(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    environment: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
) -> PaginatedResponse[DeploymentResponse]:
    base = select(ProductionDeploymentEvent).where(
        ProductionDeploymentEvent.tenant_id == tenant_id,
        ProductionDeploymentEvent.repo_id == repo.id,
    )
    if environment:
        base = base.where(ProductionDeploymentEvent.environment_name == environment)
    if since:
        base = base.where(ProductionDeploymentEvent.deployed_at >= since)
    if until:
        base = base.where(ProductionDeploymentEvent.deployed_at <= until)

    total_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    result = await session.execute(
        base.order_by(ProductionDeploymentEvent.deployed_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    deployments = result.scalars().all()

    return PaginatedResponse(
        items=[DeploymentResponse.model_validate(d) for d in deployments],
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )
```

Remove the `repo_id: uuid.UUID | None = Query(None)` param and the `if repo_id:` conditional block.

- [ ] **Step 5: Run deployment tests**

Run: `cd server && python -m pytest tests/test_deployments.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/deployments.py server/tests/test_deployments.py server/tests/conftest.py
git commit -m "require repo_id on deployments list endpoint"
```

---

### Task 3: Update pull-requests list endpoint

**Files:**
- Modify: `server/app/routes/pull_requests.py`
- Modify: `server/tests/test_pull_requests.py`

- [ ] **Step 1: Update PR list tests to pass `repo_id`**

In `server/tests/test_pull_requests.py`, update imports:

```python
from tests.conftest import mock_result, mock_count_result, make_pr, make_deployment, REPO_ID
```

Change `test_list_pull_requests`:
```python
response = await client.get(f"/api/pull-requests?repo_id={REPO_ID}")
```

Change `test_list_pull_requests_empty`:
```python
response = await client.get(f"/api/pull-requests?repo_id={REPO_ID}")
```

- [ ] **Step 2: Update `pull_requests.py` to use `get_verified_repo`**

```python
from app.middleware.repo import get_verified_repo
from app.models.repository import Repository
```

Update `list_pull_requests`:
```python
@router.get("")
async def list_pull_requests(
    pagination: PaginationParams = Depends(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    repo: Repository = Depends(get_verified_repo),
    session: AsyncSession = Depends(get_session),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
) -> PaginatedResponse[PullRequestResponse]:
    base = select(PullRequest).where(
        PullRequest.tenant_id == tenant_id,
        PullRequest.repo_id == repo.id,
    )
    if since:
        base = base.where(PullRequest.merged_at >= since)
    if until:
        base = base.where(PullRequest.merged_at <= until)

    total_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    result = await session.execute(
        base.order_by(PullRequest.merged_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    prs = result.scalars().all()

    return PaginatedResponse(
        items=[PullRequestResponse.model_validate(pr) for pr in prs],
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )
```

Remove the `repo_id: uuid.UUID | None = Query(None)` param and the `if repo_id:` conditional.

- [ ] **Step 3: Run all tests**

Run: `cd server && python -m pytest -v`
Expected: ALL PASS (62 tests — 60 existing + 2 new)

- [ ] **Step 4: Commit**

```bash
git add server/app/routes/pull_requests.py server/tests/test_pull_requests.py
git commit -m "require repo_id on pull-requests list endpoint"
```

---

### Task 4: Update docs

**Files:**
- Modify: `server/README.md`
- Modify: `README.md`

- [ ] **Step 1: Update server README endpoint table**

Update the API endpoints section to note `repo_id` is now required on `GET /api/deployments` and `GET /api/pull-requests`.

- [ ] **Step 2: Update root README if it references API endpoints**

- [ ] **Step 3: Commit**

```bash
git add server/README.md README.md
git commit -m "update docs for required repo_id"
```
