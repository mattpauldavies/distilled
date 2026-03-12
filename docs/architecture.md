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

| Layer      | Directory         | Responsibility                                 |
| ---------- | ----------------- | ---------------------------------------------- |
| Routes     | `app/routes/`     | HTTP handling, request/response serialization  |
| Services   | `app/services/`   | Business logic, GitHub API, webhook processing |
| Models     | `app/models/`     | SQLAlchemy ORM, database schema                |
| Schemas    | `app/schemas/`    | Pydantic validation, API contracts             |
| Middleware | `app/middleware/` | Request-scoped context (tenant resolution)     |

### Key services

- **webhook_service** — HMAC signature verification, event handler registry
- **github_client** — JWT auth, installation token management, GitHub API wrapper
- **installation_service** — handles app installation, repo sync, environment discovery
- **deployment_service** — processes deployment_status and pull_request events
- **attribution_service** — links merged PRs to deployments via time-window heuristic
- **environment_service** — auto-detects production environments by name pattern

### Metrics service delineation

Metrics are split across three services by **computation pattern**, not data source:

- **metrics_service** — scheduled batch recompute, results persisted to dedicated tables
- **pull_request_service** — real-time queries against live data, no persistence
- **data_quality_service** — monitoring/observability of the metrics pipeline itself

| Metric               | Service      | Pattern             | Source Data       |
| -------------------- | ------------ | ------------------- | ----------------- |
| Deployment Frequency | metrics      | pre-computed daily  | deployments       |
| Lead Time            | metrics      | pre-computed weekly | PRs + deployments |
| PR Cycle Time        | metrics      | pre-computed weekly | PRs               |
| PR Throughput        | metrics      | pre-computed weekly | PRs               |
| Open PR Count        | pull_request | live query          | PRs               |
| PR Ageing            | pull_request | live query          | PRs               |
| Metrics Freshness    | data_quality | live query          | MetricsRefreshLog |
| Attribution Coverage | data_quality | live query          | PRs + deployments |

The **dashboard_service** acts as the composition layer, orchestrating all three into a unified response.

### Scheduled jobs

- Scheduled jobs will be triggered via Railway Scheduled Jobs calling authenticated internal endpoints.
- No in-process schedulers (e.g. APScheduler).
- No OS-level cron.
- All scheduled work must be idempotent. (Jobs must be safe to run multiple times.)
- All scheduled endpoints must require internal authentication.

### Data flow: webhook to deployment

1. GitHub sends `deployment_status` to `POST /api/webhooks/github`
2. HMAC signature verified against `GITHUB_WEBHOOK_SECRET`
3. Event dispatched to handler via `BackgroundTasks` (return 200 immediately)
4. Handler checks `state == "success"` and environment `is_production`
5. Creates `ProductionDeploymentEvent`
6. Attribution service links PRs merged since last deployment

### Multi-tenancy

All tables carry `tenant_id`. Currently a hardcoded seed tenant for dev. Tenant resolved per-request via middleware.

## Frontend (client/)

React 19 + Vite + TypeScript + Tailwind. Scaffold stage — proxies `/api` to backend via Vite dev server.

## Database

PostgreSQL 16 via Docker. Async access via SQLAlchemy + asyncpg. Migrations managed by Alembic.

## Auth model

GitHub App authentication (not OAuth):

- Server generates JWT signed with App private key
- JWT exchanged for installation access tokens (cached, auto-refreshed)
- Webhooks verified via HMAC-SHA256
