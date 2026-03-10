# Chief Architect Memory

## Project: Distilled

- DORA metrics platform (deployment frequency and lead time to start; later Change Failure Rate and Time to Restore Service (MTTR))
- FastAPI backend, PostgreSQL, SQLAlchemy async, Alembic
- Multi-tenant from day one (tenant_id on all tables)
- GitHub App + webhooks for event ingestion

## Key Files

- PRD: `docs/prds/001 - Deployment Detection.md`
- RFC: `docs/rfcs/001-deployment-detection.md`
- Existing code: `server/app/` (FastAPI, currently has placeholder items CRUD)

## Architecture Decisions

- No raw webhook storage — direct processing, structured logging
- Async Postgres via asyncpg
- Tenant resolution via middleware (hardcoded seed for dev)

## Review Findings (RFC 001)

- PRIMARY ISSUE: `workflow_run` webhook doesn't natively carry environment info. `deployment_status` is the canonical webhook for environment-based detection. Needs resolution before impl.
- PRD specifies `org_id` on deployment events but RFC omits it entirely. Needs alignment.
- `ProductionDeploymentEvent` should be immutable (remove updated_at)
- Need unique constraints specified: `(tenant_id, repo_id, name)` for Environment, etc.
- Attribution time-window heuristic undefined for first deployment
- `BackgroundTasks` is at-most-once; acceptable for MVP but should be documented
- Project structure labels `domain/` but contains only DTOs/enums — anemic model risk

## Patterns to Watch

- See `patterns.md` for DDD patterns in this codebase
