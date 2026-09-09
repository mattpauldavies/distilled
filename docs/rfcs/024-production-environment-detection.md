# RFC 024: Production Environment Name Detection

---

## Summary

Production environments are auto-detected by an **exact-match** regex, so a GitHub
Environment named `distilled / production` — or `prod-eu`, or `web:live` — is stored with
`is_production = False`. Its `deployment_status` webhooks are then silently skipped, and
the repo's deployment frequency and lead time stay empty with no user-visible signal.

This RFC replaces the anchored pattern with a **substring** match: any environment whose
name contains `prod` or `live` (case-insensitive, anywhere in the string) is production. A
data migration backfills existing rows so the change takes effect for tenants that are
already onboarded.

---

## Background

`detect_production` (`server/app/services/environment_service.py`) is the only classifier:

```python
PRODUCTION_PATTERN = re.compile(r"^(production|prod|live)$", re.IGNORECASE)
```

It runs once per environment, inside `discover_environments`, at the moment an environment
is first seen. The result is persisted to `environments.is_production`.

The ingest path (`ingest_deployment_service.handle_deployment_status_event`) looks the
environment up by exact name **and** `is_production is True`:

```python
Environment.name == env_name,
Environment.is_production.is_(True),
```

Exact name equality is not the problem — GitHub sends `deployment.environment` verbatim and
`discover_environments` stored it verbatim, so the names match. The classification is what
fails. The handler returns `SKIPPED` with an info-level log (`"non-prod environment=%s,
skipping"`), so there is no deployment event, no PR attribution, and no error anywhere the
user can see.

`PATCH /environments/{env_id}` can flip `is_production` manually, but no client code calls
it, so in practice the auto-detection result is final.

## Design Decisions

### 1. Substring match, not segment match

The new pattern is:

```python
PRODUCTION_PATTERN = re.compile(r"prod|live", re.IGNORECASE)
```

matched with `re.search`. `production` is dropped from the alternation because `prod` is a
prefix of it — listing both would be redundant, not more permissive.

A segment-aware alternative was considered (split on `/`, `-`, `_`, `:`, whitespace and
match each segment exactly). It was rejected as under-inclusive for the real-world names we
want to catch — `prod-eu`, `useast1prod`, `distilled/production-web`.

**Accepted consequence:** substring matching is deliberately greedy. `preprod`,
`prod-canary`, and `staging-prod-mirror` are all classified as production, as is anything
containing `live` (`delivery-test`). This is a knowingly false-positive-leaning trade:
a missed production deployment is invisible and corrupts DORA metrics downward, whereas an
over-counted environment is visible in the deployment list and correctable via
`PATCH /environments/{env_id}`. No deny-list is added — a `preprod|staging|preview` exclusion
would reintroduce exactly the guessing this RFC removes, and the manual override is the
intended escape hatch.

### 2. Backfill via data migration

`discover_environments` uses `ON CONFLICT DO NOTHING`, so existing rows are never
re-classified — without a backfill the fix would only apply to environments discovered
after deploy. The migration flips `is_production` to true for stored names matching the new
pattern:

```sql
UPDATE environments SET is_production = true
WHERE is_production = false AND (name ILIKE '%prod%' OR name ILIKE '%live%')
```

`ILIKE` mirrors the Python pattern's case-insensitive substring semantics exactly.

**Accepted consequence:** the schema has no column recording whether `is_production` was set
by detection or by a human, so a deliberate manual override to `false` on a `prod`-containing
name would be undone. Since no client surface calls the PATCH route, no such override is
expected to exist in practice.

The downgrade reverts only the rows the new pattern catches and the old one did not, leaving
exact-match names (`production`, `prod`, `live`) alone.

### 3. Detection stays at discovery time

Classification remains a one-shot decision taken when an environment is first seen, not a
predicate evaluated per deployment. Deployment ingest continues to read the stored boolean,
so the classifier's cost and behaviour stay off the webhook hot path.

## Out of Scope

Two adjacent gaps in the same flow are **not** addressed here, and either can still cause a
`distilled / production` deployment to be missed:

1. **Environments are only discovered at install time.** `_discover_repo_environments` runs
   on `installation.created` and `installation_repositories.added` only. An environment
   created on an already-connected repo is never discovered, so ingest skips its deployments
   because no `Environment` row exists at all. Reinstalling the App is currently the only
   refresh path.
2. **The `is_production` override has no UI.** `PATCH /environments/{env_id}` exists but has
   no client consumer, so correcting a misclassification needs a raw API call.

---

## Implementation Plan

Red/green TDD throughout: write the failing test, watch it fail, implement, watch it pass.

### Task 1 — Relax the classifier

1. Extend the `test_detect_production` parametrisation in
   `server/tests/test_environment_service.py` with the names the anchored pattern rejects:
   `distilled / production`, `production-us`, `prod-eu`, `web:live`, `useast1prod` → `True`;
   and the greedy cases we accept: `preprod` → `True`. Keep `staging`, `dev`, `""` → `False`.
   Watch them fail.
2. Change `PRODUCTION_PATTERN` to `re.compile(r"prod|live", re.IGNORECASE)` and
   `detect_production` to use `re.search`. Watch them pass.

3. Add a `discover_environments` test asserting the persisted `is_production` value for
   `distilled / production` is `True`, so the classifier stays wired to the stored column.

Note that `production-us` currently asserts `False` in the existing test — that assertion is
the bug this RFC fixes and flips to `True`.

### Task 2 — Backfill migration

1. New Alembic revision, `down_revision = "d4e5f6a7b8c9"` (current head).
2. `upgrade()` runs the `UPDATE ... ILIKE` above; `downgrade()` reverts rows matching the new
   pattern but not `^(production|prod|live)$`.
3. Verify against a local database: `make migrate`, confirm a seeded
   `distilled / production` row flips to `is_production = true`.

### Task 3 — Documentation

1. `docs/architecture.md` — the `environment_service` bullet describes the matching rule.
2. `docs/metrics.md` — note how an environment qualifies as production for the setup check.
