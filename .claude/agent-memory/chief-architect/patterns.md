# DDD Patterns — Distilled

## Aggregate Boundaries (to establish)
- `Repository` should be the aggregate root for environments and deployments
- `DeploymentAttribution` is a link/value object, not an entity — use composite PK (deployment_id, pr_id)
- `ProductionDeploymentEvent` is an immutable fact record, not a mutable entity

## Webhook Processing
- GitHub webhook idempotency: de-duplicate by `run_id` for deployments, `(repo_id, number)` for PRs
- `BackgroundTasks` is fire-and-forget — events lost on crash. Acceptable for MVP.
- Must handle GitHub retries gracefully (unique constraints on all upsert targets)

## GitHub API Nuances
- `workflow_run` webhook does NOT carry environment info natively
- `deployment_status` webhook carries environment directly — preferred for environment-based detection
- Jobs API fetch required if using `workflow_run` as trigger (rate-limit concern)
