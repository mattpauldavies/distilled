# Engineering Practice

**Status:** Shipped
**Consolidates:** PRD 003 (better Python tests), RFC 003, RFC 004 (client testing), RFC 012 (demo data seed), RFC 014 (linting), RFC 022 (architecture review remediation), ADR 003 (transaction boundaries), ADR 004 (query placement and domain predicates)

## Summary

How we test, how we lint, how we get realistic data locally, and the conventions that keep
the layers honest. These are the rules a reviewer can apply on sight.

## Testing

**Integration-style over isolated units, on both tiers.** Test through the FastAPI app and
through rendered React components. Over-isolated unit tests describe the implementation
rather than the behaviour, and they are the ones that break on every refactor without ever
catching a bug.

**Server.** Tests drive the app via `httpx.AsyncClient` with dependency overrides for the
session, auth, and verified repo. Shared fixtures and model factories live in `conftest.py`.
Services are also tested directly with a mock session where the logic is worth isolating.

A caveat the mock session makes easy to miss: a mocked `execute()` will happily return
whatever shape the test configures, including shapes a real query could never produce. Tests
that exercise a select and consume it with `scalar_one`, `scalar_one_or_none`, or
`scalars().one()` need care — see the `server-query-tests` skill for the pattern.

**Client.** Vitest with jsdom, MSW intercepting HTTP at the boundary with
`onUnhandledRequest: 'error'` so an unmocked request fails loudly, factory functions for
fixtures, and a custom `render` that supplies the providers. Chart components are excluded:
canvas does not work under jsdom.

**End to end.** Playwright smoke tests in `e2e/` run against the real stack with demo seed
data.

**Coverage.** High coverage is a floor, not a target. Testing core use cases well beats
over-fitting tests to lift a number — the acceptance bar is that the suite is not fragile.

**Red then green.** Write the failing test, watch it fail for the reason you expect, then
implement.

## Linting and formatting

- **Server:** Ruff for linting and formatting, mypy for type checking.
- **Client:** ESLint flat config with typescript-eslint and the React plugins, plus Prettier
  with `eslint-config-prettier` so the two do not fight.
- **CI checks, it does not fix.** Developers fix locally. No pre-commit hooks — opt-in only.

Commands are wrapped in the Makefile; see the `distilled-dev-commands` skill for the
canonical invocations.

## Demo data

`make seed-demo` populates six months of realistic delivery data for a fictional
`acme-corp` org; `make seed-reset` removes it. Two repos tell two stories: `acme-corp/web`
is steady and healthy throughout, `acme-corp/api` starts healthy, deteriorates into a rough
patch around months three and four, and recovers. The rough patch matters — it produces
weeks with zero deployments, which is the sparse-data case the charts must handle.

Generation is deterministic (`random.Random(42)`) so re-seeding after a reset produces
identical data, and idempotent — the script checks for the demo installation before
inserting.

**The seed inserts raw rows only and then calls the same recompute pipeline the scheduled
job uses.** It previously carried its own copies of the lead time, cycle time, P75, and
week-bucketing logic, and they had drifted: lead time was measured from `opened_at` instead
of `merged_at`, with a different P75 rank. Demo data was showing numbers the production
algorithm would never produce. Deriving them through the real pipeline deletes about 130
lines and makes drift structurally impossible.

## Conventions

### Transaction boundaries — entry points commit, services flush

Entry points own the transaction: HTTP route handlers, the webhook dispatcher (which commits
per handler and rolls back on failure), and scripts. Services may `flush()` to obtain
generated IDs or surface constraint errors early, but must not `commit()` — the caller
decides when the unit of work is complete.

Without this convention, every new feature guesses, and a service that commits early makes it
impossible for its caller to roll the whole request back.

**One documented exception:** `user_service.get_or_create_user` commits its own user and
workspace creation. Provisioning must persist independently of whether the triggering request
later fails, and the commit is integral to the `IntegrityError` handling for concurrent first
logins. Auth-time provisioning is its own entry point.

A reviewer can reject a `commit()` inside `app/services/` on sight, except that one.

### Query placement

1. **Simple list and detail reads may query inline in the route.** Forcing a service layer
   onto trivial CRUD adds indirection without value. The shared count-then-page pattern lives
   in `app/services/pagination.py::paginate`.
2. **Anything with aggregation, joins across contexts, or domain rules goes in a service.**
3. **Core domain filters are defined once on the model** as class-level predicate builders:
   `PullRequest.merged_on_branch(...)` and `PullRequest.open_on_branch(...)`. "Merged PRs on
   the default branch" is the product's most consequential filter and was previously
   copy-pasted across seven call sites, where one missed clause would have silently changed a
   metric.
4. **Services never raise HTTP concerns.** Framework-free errors are translated to
   `HTTPException` at the boundary, so services stay usable from scripts and future workers.

### Service naming

A role prefix says where a module sits in the pipeline: `ingest_*` consumes webhook events,
`batch_*` runs on the scheduler, `read_*` serves queries. Unprefixed modules
(`webhook_service`, `attribution_service`, `environment_service`, the identity services,
`github_client`, `pagination`) are shared domain logic or infrastructure rather than one
pipeline stage.

### `app/middleware/` holds dependencies, not middleware

The package contains per-route FastAPI dependencies. Cross-cutting ASGI middleware — CORS,
security headers, rate limiting — lives in `app/main.py`. A rename to `app/dependencies/` was
applied and then reverted on review in favour of the established name; the distinction is
documented instead.

## The September 2026 architecture review

A full DDD and clean-architecture review of both tiers found the codebase structurally sound
but identified drift that would compound. Everything accepted was fixed in one change. The
findings worth remembering as patterns:

- **A schema can contradict its model and nobody notices until production.** The PR response
  schema declared `merged_at: datetime` while the column is nullable, so listing any open PR
  returned a 500.
- **Duplicated algorithms drift.** The demo seed, above.
- **Mixed auth on one router is a loaded gun.** Internal cron routes now live in their own
  router — see [005 Security](005-security.md).
- **Writes belong in services.** The refresh-log upsert — the write side of the freshness
  monitoring that the data-quality service reads — sat inline in a route handler.
- **Duplication hides in plain sight.** The count-then-page block appeared in three routers;
  two chart components were byte-for-byte identical apart from a name and an aria-label; a
  windowed metric was fetched twice because the card and the panel each called the same hook.
- **A missing error state is a lie.** A failed chart request rendered "No data for this
  period".
- **Tests must not depend on a developer's local `.env`.** One unpinned variable in the
  vitest config meant 19 failures for anyone who had it set.

## History

- **PRD 003 / RFC 003** established the server test suite and its patterns.
- **RFC 004 (client testing)** did the same for the client. Note two RFCs were numbered 004.
- **RFC 012** added the demo seed.
- **RFC 014** added Ruff, mypy, and Prettier.
- **RFC 022 / ADR 003 / ADR 004** ran the architecture review, applied the fixes, and
  recorded the conventions above.
