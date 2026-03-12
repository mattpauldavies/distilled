# RFC 001: Deployment Detection

## Summary

Backend system for detecting production deployments via GitHub Environments and linking PRs to those deployments. Foundation for first two DORA metrics (deployment frequency, lead time for changes).

## Approach

- **GitHub App + webhooks** for real-time event ingestion
- **Direct processing** — no raw payload storage. Extract structured domain data inline, log for forensics.
- **PostgreSQL** with SQLAlchemy (async) + Alembic migrations
- **Tenant-aware from day one** — `tenant_id` on all tables, hardcoded seed tenant for dev

---

## Domain Model

### Tenant

| Field      | Type     | Notes |
| ---------- | -------- | ----- |
| id         | UUID     | PK    |
| name       | str      |       |
| created_at | datetime |       |
| updated_at | datetime |       |

### GitHubInstallation

| Field            | Type     | Notes                    |
| ---------------- | -------- | ------------------------ |
| id               | UUID     | PK                       |
| tenant_id        | UUID     | FK → Tenant              |
| installation_id  | int      | GitHub's installation ID |
| account_login    | str      | GitHub org/user login    |
| account_type     | str      | `organization` or `user` |
| access_token     | str      | Encrypted                |
| token_expires_at | datetime |                          |
| created_at       | datetime |                          |
| updated_at       | datetime |                          |

### Repository

| Field           | Type     | Notes                   |
| --------------- | -------- | ----------------------- |
| id              | UUID     | PK                      |
| tenant_id       | UUID     | FK → Tenant             |
| installation_id | UUID     | FK → GitHubInstallation |
| github_id       | int      | GitHub's repo ID        |
| full_name       | str      | e.g. `org/repo`         |
| default_branch  | str      |                         |
| created_at      | datetime |                         |
| updated_at      | datetime |                         |

### Environment

| Field         | Type     | Notes                     |
| ------------- | -------- | ------------------------- |
| id            | UUID     | PK                        |
| tenant_id     | UUID     | FK → Tenant               |
| repo_id       | UUID     | FK → Repository           |
| name          | str      | GitHub environment name   |
| is_production | bool     | Auto-detected or user-set |
| created_at    | datetime |                           |
| updated_at    | datetime |                           |

### ProductionDeploymentEvent

Immutable — events are facts, no `updated_at`.

| Field            | Type     | Notes                          |
| ---------------- | -------- | ------------------------------ |
| id               | UUID     | PK                             |
| tenant_id        | UUID     | FK → Tenant                    |
| repo_id          | UUID     | FK → Repository                |
| environment_name | str      |                                |
| deployment_id    | int      | GitHub's deployment ID         |
| commit_sha       | str      |                                |
| ref              | str      |                                |
| started_at       | datetime |                                |
| completed_at     | datetime |                                |
| deployed_at      | datetime | Defaults to completed_at       |
| html_url         | str      | Link to workflow run on GitHub |
| created_at       | datetime |                                |

### PullRequest

| Field            | Type     | Notes                         |
| ---------------- | -------- | ----------------------------- |
| id               | UUID     | PK                            |
| tenant_id        | UUID     | FK → Tenant                   |
| repo_id          | UUID     | FK → Repository               |
| github_id        | int      | GitHub's PR ID                |
| number           | int      |                               |
| title            | str      |                               |
| base_ref         | str      | Target branch (for filtering) |
| merged_at        | datetime |                               |
| merge_commit_sha | str      |                               |
| head_sha         | str      |                               |
| author_login     | str      |                               |
| html_url         | str      | Link to PR on GitHub          |
| created_at       | datetime |                               |
| updated_at       | datetime |                               |

### DeploymentAttribution

Composite PK — a PR is attributed to a deployment exactly once.

| Field         | Type     | Notes                              |
| ------------- | -------- | ---------------------------------- |
| deployment_id | UUID     | PK, FK → ProductionDeploymentEvent |
| pr_id         | UUID     | PK, FK → PullRequest               |
| tenant_id     | UUID     | FK → Tenant                        |
| created_at    | datetime |                                    |

### Unique Constraints

| Entity                    | Constraint                              |
| ------------------------- | --------------------------------------- |
| GitHubInstallation        | `(tenant_id, installation_id)`          |
| Repository                | `(tenant_id, github_id)`                |
| Environment               | `(tenant_id, repo_id, name)`            |
| ProductionDeploymentEvent | `(tenant_id, deployment_id)`            |
| PullRequest               | `(tenant_id, repo_id, number)`          |
| DeploymentAttribution     | `(deployment_id, pr_id)` (composite PK) |

---

## Webhook Infrastructure

### Entry point

- `POST /api/webhooks/github` — single receiver
- HMAC-SHA256 signature verification using webhook secret
- Event type → handler dispatch via dict mapping
- Processing via FastAPI `BackgroundTasks` (return 200 immediately)
- Structured logging on receipt

### Events handled

| Event                          | Trigger                   | Action                                              |
| ------------------------------ | ------------------------- | --------------------------------------------------- |
| `installation`                 | App installed/uninstalled | Create/update GitHubInstallation, sync repos        |
| `deployment_status` (success)  | Deployment succeeds       | Check if prod environment → create deployment event |
| `pull_request` (closed+merged) | PR merged                 | Upsert PullRequest, trigger attribution             |

### GitHub API Client

- Thin `httpx` async wrapper
- JWT → installation access token flow (auto-refresh)
- Used for: listing environments, historical backfill

---

## Detection Logic

### Production environment detection

1. On repo sync → fetch environments via GitHub API
2. Auto-match against allowlist: `production|prod|live` (case-insensitive)
3. Match found → `is_production = True`
4. No match → leave unset, surface via API for user selection

### Deployment detection (on `deployment_status`)

1. Check `state == "success"`
2. Extract `environment` name from the event payload (carried natively)
3. If environment matches one where `is_production == True` → create `ProductionDeploymentEvent`
4. De-duplicate by GitHub `deployment_id` (unique constraint)

### PR → Deployment attribution

- Triggered after each new deployment event
- **MVP heuristic:** PRs with `merged_at` between `previous_deployment.deployed_at` and `current_deployment.deployed_at` for that repo
- Only attributes PRs where `base_ref == repo.default_branch`
- For first deployment in a repo, uses 30-day lookback window as lower bound
- Creates `DeploymentAttribution` record (INSERT ON CONFLICT DO NOTHING for idempotency)

---

## API Endpoints

```
POST   /api/webhooks/github                    — webhook receiver

GET    /api/repos                              — list repos for tenant
GET    /api/environments                       — list environments (optional ?repo_id=)
PATCH  /api/environments/{env_id}              — toggle is_production

GET    /api/deployments                        — list deployments (filter: repo, date range)
GET    /api/deployments/{id}                   — deployment detail + attributed PRs

GET    /api/pull-requests                      — list PRs (filter: repo, date range)
GET    /api/pull-requests/{id}                 — PR detail + linked deployment
```

All list endpoints paginated. Tenant resolved from context (hardcoded seed for dev).

---

## Project Structure

```
server/app/
├── main.py
├── config.py
├── db/
│   ├── base.py               # async engine + session factory
│   └── models/               # SQLAlchemy ORM models
├── schemas/                  # Pydantic request/response schemas
├── routes/
│   ├── health.py
│   ├── webhooks.py
│   ├── repos.py
│   ├── deployments.py
│   └── pull_requests.py
├── services/
│   ├── webhook_service.py    # signature verification, event dispatch
│   ├── github_client.py      # GitHub API wrapper
│   ├── installation_service.py
│   ├── deployment_service.py
│   ├── attribution_service.py
│   └── environment_service.py
└── middleware/
    └── tenant.py             # tenant resolution (hardcoded for now)
```

### Dependencies (new)

- `sqlalchemy[asyncio]` + `asyncpg`
- `alembic`
- `httpx`
- `PyJWT` + `cryptography`
- `pytest` + `pytest-asyncio` + `httpx` (dev)

---

## Decisions

- **No raw webhook storage** — process inline, log for forensics. Scales better.
- **No data quality scoring** — removed from scope.
- **No detection/attribution method enums** — single approach for each, no need to track.
- **`deployment_status` over `workflow_run`** — carries environment natively, no extra API calls needed per workflow run.
- **Immutable deployment events** — events are facts, no `updated_at`.
- **Composite PK on attribution** — `(deployment_id, pr_id)` enforces uniqueness naturally.
- **`org_id` deferred** — `repo.full_name` contains org. First-class org entity added when multi-org support needed.
- **Async Postgres** — matches FastAPI async pattern, ready for production load.
- **Tenant-aware schema** — `tenant_id` everywhere, avoids painful retrofit later.

## Known Limitations (MVP)

- **At-most-once webhook processing** — `BackgroundTasks` is in-process. Server crash mid-processing loses the event. GitHub won't retry (we return 200 immediately). Acceptable for MVP; structured logging provides forensics.
- **No retry on GitHub API failure** — if environment listing fails during repo sync, logged but not retried. Historical backfill can recover.
- **30-day lookback on first deployment** — PRs merged more than 30 days before the first detected deployment won't be attributed.
