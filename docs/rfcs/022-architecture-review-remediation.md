# RFC 022 — Architecture Review and Remediation

**Date:** 2026-09-08
**Status:** Implemented
**Scope:** Domain-driven design / clean architecture review of `/server` and `/client`, with fixes applied. Security was reviewed separately (RFCs 015, 017) and is out of scope here.

---

## Summary

A full architecture review of both tiers found the codebase structurally sound — the layered
backend and the client's `useMetricSection` abstraction are good foundations — but identified
a set of drift, duplication, and boundary problems that would compound as the codebase grows.
All accepted findings were remediated in this change; the conventions they established are
recorded in ADR 003 (transaction boundaries) and ADR 004 (query placement and domain
predicates).

---

## Server findings and remediation

### S1 — API schema contradicted the model: `merged_at` non-optional (HIGH — fixed)

`schemas/pull_requests.py` declared `merged_at: datetime` while the column is nullable, so
listing any open PR raised a validation error and returned 500. Fixed to
`datetime | None`, with a regression test (`test_list_pull_requests_includes_open_pr`).

### S2 — Demo seed re-implemented the metric algorithms, and had drifted (HIGH — fixed)

`scripts/seed_demo.py` carried its own copies of the lead time, cycle time, P75, and
week-bucketing logic — and they disagreed with `metrics_service` (lead time measured from
`opened_at` instead of `merged_at`; a different P75 rank). Demo data therefore showed numbers
the production algorithm would never produce. The script now inserts raw rows only and calls
`metrics_service.recompute_repo_and_log` per repo, deleting ~130 lines and making drift
structurally impossible. Verified end-to-end against a live database.

### S3 — Internal cron endpoints shared a router with the dashboard API (MEDIUM — fixed)

`/metrics/recompute` and `/metrics/recompute-targets` (cron-secret auth) lived in the same
router as the user-facing `/metrics/*` endpoints (Clerk auth), which forced auth to be
declared per-route — one forgotten declaration would have been an unauthenticated endpoint,
as the old `main.py` comment admitted. They now live in `routes/internal.py` with the
cron-secret check at router level; the metrics router gets `require_auth` at router level in
`main.py` like every other router. URL paths are unchanged (pinned by Railway cron and
`scripts/run_hourly_recompute.py`).

### S4 — The data-quality write lived in a route handler (HIGH — fixed)

The `MetricsRefreshLog` upsert — the write side of the freshness monitoring that
`data_quality_service` reads — sat inline in the recompute route. Moved into
`metrics_service.recompute_repo_and_log`; the route now validates, delegates, and commits.

### S5 — Live queries hiding in the batch-compute service (MEDIUM — fixed)

`metrics_service` hosted three live aggregates (`get_lead_time_aggregate`,
`get_pr_cycle_time_aggregate`, `get_pr_throughput_summary`) that contradicted the documented
"pre-computed vs live" service split. Moved to `pull_request_service`; the delineation table
in `docs/architecture.md` now distinguishes pre-computed weekly series from live headline
numbers.

### S6 — The core domain filter was copy-pasted seven times (MEDIUM — fixed)

"Merged PRs on the default branch" and "open PRs" existed only as repeated where-clause
spellings across metrics, data-quality, and pull-request queries. Now defined once as
`PullRequest.merged_on_branch(...)` and `PullRequest.open_on_branch(...)` class predicates
(ADR 004).

### S7 — Count-then-page pattern duplicated across three routers (MEDIUM — fixed)

Extracted `app/services/pagination.py::paginate`, deleting the triplicated count/offset/limit
assembly in repos, deployments, and pull-requests routes.

### S8 — HTTP concerns leaking into the service layer (MEDIUM — fixed)

`clerk_service` raised `HTTPException` with status codes, coupling the JWT verifier to
FastAPI. It now raises a framework-free `AuthError`, translated to 401 in `app/auth.py`.

### S9 — PR ingestion had no named home (MEDIUM — fixed)

`handle_pull_request_event` lived inside `deployment_service` along with accreted helpers.
Extracted to `pr_ingestion_service`; shared payload-parsing helpers (`parse_datetime`,
`validate_github_url`) moved to `webhook_service`. Tests split accordingly.

### S10 — `app/middleware/` contained dependencies, not middleware (LOW — documented, not renamed)

The package holds per-route FastAPI dependencies rather than ASGI middleware. A rename to
`app/dependencies/` was applied and then reverted on review — the established name was
preferred. The distinction is now documented in the package docstring and in
`docs/architecture.md` instead.

### S11 — Smaller fixes (LOW — fixed)

- Dead `has_production_environment` helper deleted (production code used a different path).
- Duplicated GitHub-identity extraction in `user_service` unified into
  `_extract_github_identity`.
- Webhook route's bare-status-code error style documented as deliberate.

### Deferred (unchanged from previous reviews)

- Async webhook processing with retry/DLQ (RFC 015 ARCH-004) — separate RFC required.
- Shared multi-worker GitHub token cache (RFC 015 ARCH-003) — infrastructure change.

---

## Client findings and remediation

### C1 — Every windowed metric fetched twice (HIGH — fixed)

Card and chart-panel components each called the same hook, so deployment frequency, lead
time, and cycle time fired two identical requests per repo/window change, and Retry on a card
did not refresh the matching panel. `Dashboard.tsx` now calls each hook exactly once and
passes the `MetricSection<T>` down; all `components/metrics/*` are purely presentational. A
test asserts each endpoint is requested exactly once per mount.

### C2 — Chart panels rendered fetch errors as "no data" (HIGH — fixed)

`ChartPanel` had no error state, so a failed request showed "No lead time data for this
period" — factually wrong. It now mirrors `MetricCard`'s "Failed to load" + Retry branch.

### C3 — Two byte-for-byte duplicate chart components (MEDIUM — fixed)

`LeadTimeChart` and `CycleTimeChart` differed only in name and aria-label. Merged into
`WeeklyPercentilesChart` with an `ariaLabel` prop; `toHours` moved to `lib/format.ts`.

### C4 — Sentry initialised after sign-in (MEDIUM — fixed)

`Sentry.init` ran in a `useEffect` inside the signed-in `Home` component, so errors during
sign-in or in the top-level `ErrorBoundary` were never reported. Moved to module scope in
`main.tsx`.

### C5 — `useRepos` re-implemented the fetch state machine (MEDIUM — accepted as-is)

Originally consolidated into `useMetricSection`, but RFC 021 (multi-user tenants) landed
first and gave `useRepos` genuinely distinct behaviour — it gates on active-tenant
resolution — so the consolidation no longer applies and main's version was kept.
`useMetricSection`'s `loading` initialiser was still corrected to `Boolean(path)` to avoid
a first-frame flash.

### C6–C9 — Smaller fixes (LOW — fixed)

- `SectionStatus` / `FreshnessStatus` literal unions replace stringly-typed `status` fields.
- Query strings built with `URLSearchParams` (values now URL-encoded).
- The `eslint-disable react-hooks/exhaustive-deps` suppressions in `useMetricSection` and
  `OnboardingScreen` removed; test mocks fixed to provide a referentially stable `getToken`,
  matching real Clerk behaviour.
- `timeAgo` moved from `Dashboard.tsx` to `lib/format.ts`.

### C0 — Test suite depended on the developer's local `.env` (HIGH — fixed)

`vite.config.ts` pinned two env vars for tests but not `VITE_API_BASE_URL`, so a developer
with that variable set locally saw 19 test failures (absolute URLs bypassing MSW's relative
handlers). Pinned to `""` in the vitest env.

---

## Verification

- Server: 240 tests passing (after rebasing onto RFC 020/021 work); ruff and mypy clean.
- Client: 62 tests passing; ESLint, Prettier, and `tsc --noEmit` clean.
- Seed script run against a live local database; all four metric tables and the refresh log
  populated by the production pipeline with `success` status.
