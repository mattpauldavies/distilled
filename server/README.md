# Server

FastAPI backend for deployment detection and DORA metrics. Ingests GitHub webhooks, detects production deployments, and attributes PRs to deployments.

## Setup

```sh
cp .env.example .env  # edit as needed
poetry install
make db-up            # start Postgres
make migrate          # apply migrations
```

## Run

```sh
poetry run uvicorn app.main:app --reload --port 8000
```

## API docs

http://localhost:8000/docs (Swagger UI) or http://localhost:8000/redoc

## Structure

```
app/
  main.py          # App factory, lifespan, router registration
  config.py        # Settings via pydantic-settings (.env)
  logging.py       # Dev-mode file logging setup
  db.py            # Async SQLAlchemy engine + session factory
  models/          # ORM models (database tables)
  schemas/         # Pydantic request/response shapes (API contract)
  routes/          # FastAPI routers (HTTP layer)
  services/        # Business logic (webhook handling, GitHub API, attribution)
  middleware/      # Request-scoped context (tenant resolution)
database/          # Alembic migrations
```

## Environment variables

| Variable                  | Description                              | Default                                                             |
| ------------------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| `DATABASE_URL`            | Async Postgres connection string         | `postgresql+asyncpg://distilled:distilled@localhost:5432/distilled` |
| `GITHUB_APP_ID`           | Numeric GitHub App ID                    | —                                                                   |
| `GITHUB_PRIVATE_KEY_PATH` | Path to `.pem` private key file          | —                                                                   |
| `GITHUB_WEBHOOK_SECRET`   | Webhook secret from GitHub App settings  | —                                                                   |
| `SEED_TENANT_ID`          | Dev tenant UUID                          | `00000000-0000-0000-0000-000000000001`                              |
| `SEED_TENANT_NAME`        | Dev tenant name                          | `dev`                                                               |
| `ENVIRONMENT`             | `development` enables local file logging | `production`                                                        |
| `INTERNAL_CRON_SECRET`    | Bearer token for scheduled recompute     | —                                                                   |

## API endpoints

| Method | Path                                    | Description                                                     |
| ------ | --------------------------------------- | --------------------------------------------------------------- |
| GET    | `/api/health`                           | Health check                                                    |
| POST   | `/api/webhooks/github`                  | GitHub webhook receiver (HMAC verified)                         |
| GET    | `/api/repos`                            | List repos for tenant (paginated)                               |
| GET    | `/api/repos/{id}/environments`          | List environments for a repo                                    |
| PATCH  | `/api/repos/{id}/environments/{env_id}` | Toggle `is_production`                                          |
| GET    | `/api/deployments`                      | List deployments (requires `repo_id`, filter: env, date range)  |
| GET    | `/api/deployments/{id}`                 | Deployment detail + attributed PRs                              |
| GET    | `/api/pull-requests`                    | List PRs (requires `repo_id`, filter: date range)               |
| GET    | `/api/pull-requests/{id}`               | PR detail + linked deployment                                   |
| POST   | `/api/metrics/recompute`                | Trigger per-repo metric recompute (Bearer auth)                 |
| GET    | `/api/metrics/deployment-frequency`     | Deployment frequency (daily counts, 30/60/90 day window)        |
| GET    | `/api/metrics/lead-time`                | Lead time percentiles (weekly, coverage %, 30/60/90 day window) |
| GET    | `/api/metrics/open-prs`                 | Open PR counts (total, live, draft)                             |
| GET    | `/api/metrics/pr-ageing`                | PR age distribution (<2d, 2-7d, 7-14d, >14d buckets)            |

## Local dev logging

When `ENVIRONMENT=development` (set in `.env`), logs are written to `logs/dev.log` in addition to stdout.
The file is truncated on each app restart. In production (default), only stdout logging is used.
The `logs/` directory is gitignored.

## Webhook events

| Event                                          | Trigger             | Action                                                 |
| ---------------------------------------------- | ------------------- | ------------------------------------------------------ |
| `installation` (created)                       | App installed       | Upsert installation, sync repos, discover environments |
| `deployment_status` (success)                  | Deployment succeeds | Create deployment event if production environment      |
| `pull_request` (opened, reopened, closed, ...) | PR lifecycle event  | Upsert PR record (capture draft, closed_at status)     |

## Testing

```sh
make test              # run all tests
make test-coverage     # show coverage report
```

See [RFC 003: Better Python Tests](../docs/rfcs/003-better-python-tests.md) for architecture details.
