# RFC 003: Better Python Tests

## Context

Only `test_logging.py` exists (10 tests). No coverage for routes, services, or webhook handling.

## Strategy

- **Mock DB, not real Postgres** — avoids CI complexity, e2e tests later
- **Integration-style** — test through FastAPI TestClient where possible
- **Override DI deps** — `get_session` → mock session, `get_tenant_id` → fixed UUID
- **Test services directly** — pass mock sessions, verify business logic

## Test Infrastructure

### conftest.py

Shared fixtures:

- `mock_session` — AsyncMock with helper to configure execute() return chains
- `tenant_id` — fixed UUID
- `client` — httpx AsyncClient with app + overridden deps
- `make_repo()`, `make_pr()`, `make_deployment()` etc — model factories

Mock session handles these SQLAlchemy patterns:

- `result.scalar_one_or_none()` → model or None
- `result.scalar_one()` → model
- `result.scalars().all()` → list
- `commit()` / `flush()` / `rollback()` / `refresh()` → no-op

### Test Files

| File                           | Covers                             | Key scenarios                                       |
| ------------------------------ | ---------------------------------- | --------------------------------------------------- |
| `test_health.py`               | GET /api/health                    | Returns 200 + ok                                    |
| `test_repos.py`                | Repos routes                       | List (paginated), list envs, update env, 404        |
| `test_deployments.py`          | Deployments routes                 | List with filters, detail with attributed PRs, 404  |
| `test_pull_requests.py`        | PR routes                          | List with filters, detail with deployment link, 404 |
| `test_webhooks.py`             | Webhook endpoint                   | Valid/invalid signature, event dispatch             |
| `test_webhook_service.py`      | verify_signature, register_handler | Pure function tests                                 |
| `test_environment_service.py`  | detect_production                  | prod/production/live/staging/random                 |
| `test_attribution_service.py`  | attribute_prs_to_deployment        | Window calc, empty results, multiple PRs            |
| `test_deployment_service.py`   | Deployment + PR webhook handlers   | Success/skip paths, duplicate handling              |
| `test_installation_service.py` | Installation handler, sync_repos   | Created/deleted actions, repo upsert                |

### Make Commands

- `make test` — `cd server && poetry run pytest`
- `make test-coverage` — `cd server && poetry run pytest --cov=app --cov-report=term-missing`

### Dependencies

Add to dev deps: `pytest-cov`

## Implementation Plan

1. Add pytest-cov dependency
2. Write conftest.py with fixtures + factories
3. Write test files (parallelizable — each file is independent)
4. Add Make commands
5. Run tests + measure coverage
6. Iterate until >=90%
