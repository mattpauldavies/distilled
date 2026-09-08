# Architecture

## Overview

Distilled is a two-tier web app: a FastAPI backend that ingests GitHub webhooks and serves a REST API, and a React frontend that displays engineering metrics.

```
GitHub webhook ──► FastAPI ──► PostgreSQL
                      ▲
                      │
                   React UI
```

## Backend (server/)

### Layers

| Layer        | Directory           | Responsibility                                            |
| ------------ | ------------------- | --------------------------------------------------------- |
| Routes       | `app/routes/`       | HTTP handling, request/response serialization             |
| Services     | `app/services/`     | Business logic, GitHub API, webhook processing            |
| Models       | `app/models/`       | SQLAlchemy ORM, database schema, shared query predicates  |
| Schemas      | `app/schemas/`      | Pydantic validation, API contracts                        |
| Dependencies | `app/dependencies/` | FastAPI request dependencies (tenant and repo resolution) |

Cross-cutting HTTP middleware (CORS, security headers, rate limiting) lives in `app/main.py`.

Conventions the layers follow are recorded as ADRs: transaction ownership in
[ADR 003](adrs/003-transaction-boundaries.md), query placement in
[ADR 004](adrs/004-query-placement-and-domain-predicates.md).

### Key services

- **webhook_service** — HMAC signature verification, event handler registry, payload parsing helpers
- **github_client** — JWT auth, installation token management, GitHub API wrapper
- **installation_service** — handles app installation, repo sync, environment discovery
- **deployment_service** — processes deployment_status events
- **pr_ingestion_service** — processes pull_request events into the PullRequest table
- **attribution_service** — links merged PRs to deployments via time-window heuristic
- **environment_service** — auto-detects production environments by name pattern

### Metrics service delineation

Metrics are split across three services by **computation pattern**, not data source:

- **metrics_service** — scheduled batch recompute, results persisted to dedicated tables; also
  writes the `MetricsRefreshLog` row for each run
- **pull_request_service** — real-time queries against live data, no persistence
- **data_quality_service** — monitoring/observability of the metrics pipeline itself

Note the weekly **chart series** are pre-computed, but the **headline numbers** (lead time
median, cycle time median, throughput summary) are live queries so they always reflect the
selected window exactly.

| Metric                          | Service      | Pattern             | Source Data       |
| ------------------------------- | ------------ | ------------------- | ----------------- |
| Deployment Frequency            | metrics      | pre-computed daily  | deployments       |
| Lead Time (weekly series)       | metrics      | pre-computed weekly | PRs + deployments |
| Lead Time (headline median)     | pull_request | live query          | PRs + deployments |
| PR Cycle Time (weekly series)   | metrics      | pre-computed weekly | PRs               |
| PR Cycle Time (headline median) | pull_request | live query          | PRs               |
| PR Throughput (weekly series)   | metrics      | pre-computed weekly | PRs               |
| PR Throughput (summary)         | pull_request | live query          | PRs               |
| Open PR Count                   | pull_request | live query          | PRs               |
| PR Ageing                       | pull_request | live query          | PRs               |
| Metrics Freshness               | data_quality | live query          | MetricsRefreshLog |
| Attribution Coverage            | data_quality | live query          | PRs + deployments |

The core "merged PRs on the default branch" and "open PRs" filters are defined once as
class-level predicates on the `PullRequest` model (`merged_on_branch`, `open_on_branch`)
and reused by every metric query.

The **dashboard_service** exposes one helper per section; each of the `/metrics/*` endpoints delegates to its corresponding helper. The client fetches all sections in parallel, so one slow query never blocks the rest of the dashboard.

### Scheduled jobs

- Scheduled jobs will be triggered via Railway Scheduled Jobs calling authenticated internal endpoints.
- Internal endpoints live in `app/routes/internal.py` with the cron-secret check applied at
  router level; user-facing routers get `require_auth` at router level in `main.py`.
- No in-process schedulers (e.g. APScheduler).
- No OS-level cron.
- All scheduled work must be idempotent. (Jobs must be safe to run multiple times.)
- All scheduled endpoints must require internal authentication.
- The demo seed script (`scripts/seed_demo.py`) inserts raw rows only and derives metrics by
  calling the same recompute pipeline the scheduled job uses — demo numbers can never drift
  from the production algorithm.

### Data flow: webhook to deployment

1. GitHub sends `deployment_status` to `POST /webhooks/github`
2. HMAC signature verified against `GITHUB_WEBHOOK_SECRET`
3. Event dispatched to handler via `BackgroundTasks` (return 200 immediately)
4. Handler checks `state == "success"` and environment `is_production`
5. Creates `ProductionDeploymentEvent`
6. Attribution service links PRs merged since last deployment

### Multi-tenancy

All tables carry `tenant_id`. Membership is a many-to-many relationship in `tenant_users`, with a `(user_id, tenant_id, role)` row per membership and a partial unique index enforcing exactly one owner per tenant. `users.last_active_tenant_id` is a per-user default — the tenant a fresh sign-in resolves to in the absence of an explicit choice.

The active tenant for any given request is resolved as:

1. `X-Tenant-Id` header on the request, if present (membership verified at request time)
2. Otherwise, `users.last_active_tenant_id`
3. Otherwise, 409 — the user has no active tenant and the client must surface onboarding

`require_owner` is the dependency used for owner-only routes (`/team/*`); membership lookups use indexed columns and add a single join per authenticated request.

Tenant deletion is a single `DELETE FROM tenants WHERE id = ...`: every tenant-scoped FK (`repositories`, `pull_requests`, `deployment_events`, `tenant_users`, `invitations`, all metrics tables) carries `ON DELETE CASCADE`. ADR 002 documents the rationale.

## Frontend (client/)

React 19 + Vite + TypeScript + Tailwind. Calls the backend via `VITE_API_BASE_URL` (defaults to same origin in production).

## Database

PostgreSQL 16 via Docker. Async access via SQLAlchemy + asyncpg. Migrations managed by Alembic.

## Auth model

GitHub App authentication (not OAuth):

- Server generates JWT signed with App private key
- JWT exchanged for installation access tokens (cached, auto-refreshed)
- Webhooks verified via HMAC-SHA256
