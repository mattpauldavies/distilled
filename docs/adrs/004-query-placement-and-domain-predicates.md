# ADR 004 — Query Placement and Shared Domain Predicates

**Date:** 2026-09-08
**Status:** Accepted

## Context

Two competing conventions had emerged: the metrics routes delegated every query to a
service, while the repos/deployments/pull-requests/environments routes built ORM queries
inline. Separately, the product's most consequential filter — "merged PRs on the default
branch" — was copy-pasted across seven call sites, so one missed clause would silently
change a metric.

## Decision

1. **Simple list/detail reads may query inline in the route.** Forcing a service layer onto
   trivial CRUD adds indirection without value. The shared count-then-page pattern lives in
   `app/services/pagination.py::paginate`.
2. **Anything with aggregation, joins across contexts, or domain rules goes in a service**
   (`dashboard_service`, `metrics_service`, `pull_request_service`, `data_quality_service`).
3. **Core domain filters are defined once on the model** as class-level predicate builders:
   `PullRequest.merged_on_branch(...)` and `PullRequest.open_on_branch(...)`. New metric
   queries must use these rather than re-spelling the tenant/repo/branch/merged clauses.
4. **Services never raise HTTP concerns.** Framework-free errors (e.g.
   `clerk_service.AuthError`) are translated to `HTTPException` at the boundary
   (`app/auth.py`, route handlers).

## Consequences

- Routes stay thin where thinness is free, without dogmatically wrapping one-line selects.
- Metric definitions have a single source of truth; the demo seed exercises the same code
  path as production recompute.
- Services remain usable outside FastAPI (scripts, future workers).
