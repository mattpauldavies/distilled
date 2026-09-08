# RFC 023: Installation and Repository Lifecycle Events

---

## Summary

The GitHub webhook ingest path only reacts to `installation.created`. Three lifecycle events are dropped today:

1. **`installation_repositories.added`** — repos added to an existing installation never appear in Distilled.
2. **`installation_repositories.removed`** — repos removed from an installation stay visible forever.
3. **`installation.deleted`** — uninstalling the App leaves the installation and all its repos looking active (currently just logged).

This RFC adds a handler for the `installation_repositories` event and extends the `installation` handler for `deleted`, using **soft-delete** semantics: a nullable `removed_at` timestamp on both `repositories` and `github_installations`. Historical pull requests, deployments, environments, and metrics are preserved, and re-adding a repo (or re-installing the App) resurrects the records automatically.

---

## Background

- `handle_installation_event` (`server/app/services/ingest_installation_service.py`) is registered for the `installation` event. `created` upserts the installation, syncs repos from the payload, and discovers environments. `deleted` only logs.
- GitHub delivers repo membership changes as a **separate event type**, `installation_repositories`, with `action` of `added`/`removed` and `repositories_added`/`repositories_removed` arrays. No handler is registered for it, so these deliveries are silently ignored.
- `repositories` rows are referenced by `pull_requests`, `deployment_events`, `environments`, and five metrics tables. A hard delete would either violate foreign keys or destroy delivery history that the whole product exists to report on.

## Design Decisions

### 1. Soft delete via `removed_at`

Add a nullable timezone-aware `removed_at` column to `repositories` and `github_installations`.

- **`installation_repositories.removed`** stamps `removed_at = now()` on the repos whose `github_id` appears in `repositories_removed`.
- **`installation.deleted`** stamps `removed_at` on the installation **and** all of its repos.
- **Re-add / re-install** clears `removed_at` through the existing upserts' `ON CONFLICT DO UPDATE` clauses — resurrection is free.

Rejected alternatives: hard delete with cascade (destroys the metrics history the product reports on) and log-only (leaves stale repos in the UI indefinitely).

### 2. Tenant resolution by installation lookup

`installation.created` resolves the tenant through the installing user's owner membership because the installation doesn't exist yet. For `installation_repositories.*` the installation must already exist, so the handler looks up `GitHubInstallation` by `installation_id` directly. Unknown installations are logged and skipped, mirroring the existing unknown-account behaviour.

### 3. Environment discovery shared between created and added

The per-repo `list_environments` → `discover_environments` loop moves out of `_handle_created` into a helper so `added` runs the same discovery for just the new repos.

### 4. `default_branch` preserved on re-add

`installation_repositories` payload entries omit `default_branch`. The `sync_repos` conflict-update only touches `default_branch` when the payload provides it, so a re-add cannot clobber a known branch back to the `"main"` default.

### 5. Filtering scope

Only the repo list route (`GET /repos`) excludes soft-deleted rows (`removed_at IS NULL`). The repo middleware and the PR/deployment ingest lookups stay untouched: historical data remains reachable by direct navigation, and GitHub stops delivering events for removed repos anyway.

---

## Implementation Plan

Red/green TDD throughout: write the failing test, watch it fail, implement, watch it pass.

### Task 1 — Migration and models

1. Alembic migration (down_revision `c1d2e3f4a5b6`): add nullable `removed_at` (`DateTime(timezone=True)`) to `repositories` and `github_installations`.
2. Add `removed_at: Mapped[datetime | None]` to `Repository` and `GitHubInstallation` models.

### Task 2 — `installation_repositories` handler

Tests in `server/tests/test_ingest_installation_service.py`, implementation in `ingest_installation_service.py`:

1. **added**: known installation → repos from `repositories_added` upserted via `sync_repos`, environments discovered for those repos.
2. **added, unknown installation**: warning logged, no writes.
3. **removed**: repos in `repositories_removed` get `removed_at` stamped (single `UPDATE ... WHERE github_id IN (...)` scoped to tenant + installation).
4. `sync_repos` upsert clears `removed_at` and omits `default_branch` from the conflict-update when absent from the payload.

### Task 3 — `installation.deleted`

1. Replace the log-only branch: stamp `removed_at` on the matching `GitHubInstallation` and all its repos. Unknown installation → log and skip.
2. `installation.created` upsert clears `removed_at` on conflict (re-install resurrects).

### Task 4 — Route filtering

`GET /repos` adds `Repository.removed_at.is_(None)`; test that a soft-deleted repo is excluded.

### Task 5 — Docs

Update `docs/architecture.md` (webhook events table, if present) and the three READMEs only where they describe handled webhook events; note the soft-delete behaviour.

### Verification

- `pytest` green for the server suite.
- `mypy` / linting clean per repo tooling.
