# RFC 027: Release-Based Deployment Tracking

## Summary

Make "what counts as a deployment" a per-repository choice between **deployment events** (today's `deployment_status` → production environment path) and **releases** (`release.published`). The choice is set by a workspace owner on a new **Settings → Deployment Tracking** page in the profile menu.

The design deliberately changes as little as possible downstream. A release becomes a row in the existing `deployment_events` table, so deployment frequency, lead time, PR attribution, the deployments list and the batch metrics jobs all keep working untouched. The new code is one column on `repositories`, one column on `deployment_events`, one webhook handler, one PATCH endpoint, one settings page, and a source-aware `setup_required` gate.

Implements `docs/prds/018 - Release-Based Deployment Tracking.md`.

---

## Context

Deployment ingest today (`server/app/services/ingest_deployment_service.py`):

- `handle_deployment_status_event` is registered for `deployment_status` and returns early unless `deployment_status.state == "success"`.
- It looks up **every** `Repository` row with the payload's `github_id` — one per workspace tracking the repo (RFC 026 fan-out) — and, for each, requires an `environments` row for the deployment's environment name with `is_production = true`. No row, or a non-production row, and the deployment is dropped for that workspace.
- On insert it UPSERTs `ProductionDeploymentEvent` on `(tenant_id, deployment_id)` and then calls `attribute_prs_to_deployment`, which attributes PRs merged to the default branch between the previous deployment and this one.

Everything downstream reads that one table:

- `batch_metrics_service.compute_deployment_frequency` counts rows per day; `compute_lead_time` joins through `deployment_attributions`.
- `read_metrics_service.get_deployment_frequency_section` / `get_lead_time_section` / `get_pr_cycle_time_section` each call `get_production_environments(...)` **first** and return `status="setup_required"` when the repo has no production environment (`read_metrics_service.py:287,307,326`). `get_data_quality_section` reports the same fact as `setup.has_production_environment` (`read_metrics_service.py:379`).
- `routes/deployments.py` lists and filters deployments, including by `environment_name`.

Webhook plumbing (`services/webhook_service.py`): handlers register with `@register_handler("<event_type>")`; the dispatcher runs every handler for an event type in its own transaction and records the delivery as `succeeded` / `skipped` / `failed` / `no_handler`. Returning the `SKIPPED` sentinel is how a handler says "deliberately did nothing", which surfaces in `webhook_events` rather than vanishing.

Repository settings today: `repositories` carries `full_name`, `default_branch`, `removed_at`. There is no PATCH endpoint — the resource supports `GET`, `POST` (add) and `DELETE` (soft remove), all owner-gated except the list.

Client settings today: `App.tsx` holds `settingsPage: "none" | "team" | "repos"` and renders `TeamPage` / `RepositoriesPage` full-screen; `ProfileMenu` shows those two entries to owners only. Both pages head themselves `Settings · <thing>` with a "Back to dashboard" button.

### The GitHub constraint

A GitHub App may only subscribe to the `release` webhook event if it holds **Contents: read** — ["To subscribe to this event, a GitHub App must have at least read-level access for the 'Contents' repository permission"](https://docs.github.com/en/webhooks/webhook-events-and-payloads). `docs/github-app.md` currently records Contents as deliberately not requested ("Distilled reads no source code").

The gate is on **event delivery, not on reading anything**: the payload is pushed to us and no API call is involved. It applies to the event as a whole, so every action (`created`, `published`, …) sits behind the same permission — there is no narrower subscription. GitHub has no separate Releases permission; releases live under Contents, and so does every alternative route to the same signal (the Releases REST API, `push` with tag refs, the `create` tag event).

Adding the permission puts every existing installation into GitHub's "review requested permissions" state until an admin approves — during which release events are not delivered. This is the single largest cost of the feature and is recorded as ADR 011.

The one signal that needs no new permission is `workflow_run` (Actions: read, already held): "a deployment is a successful run of a named workflow". It is a weaker signal — the workflow name is a per-repo configuration string rather than a fact GitHub models — and a different feature. Noted here as the fallback if the permission widening is ever refused.

---

## Decisions

1. **Per repository, not per workspace** → `repositories.deployment_source`. A workspace typically holds services that deploy and libraries that release; one answer for all of them would be wrong for half. Default `'deployment'` for existing and new rows, so nothing changes for anyone until they ask for it.
2. **Releases land in `deployment_events`** → no second table, no union reads, no changes to metrics, attribution, or the dashboard API. The cost is a few columns that fit releases loosely (below); the benefit is that the entire read and aggregation surface is untouched.
3. **One source at a time, enforced at ingest** → each handler filters the fan-out to repositories whose `deployment_source` matches it. The other handler returns `SKIPPED`, so the drop is visible in `webhook_events` rather than silent. Counting both would double count teams that do both.
4. **`source` is recorded but never filtered on** → `deployment_events.source` exists for support, debugging and future reporting. No metric, chart or query filters by it: a repository that switches sources has one continuous deployment history, which is what the owner means by "switch". (Confirmed with the product owner: a mixture of triggers is, from the product's point of view, just a list of deployments.)
5. **Unique constraint gains `source`** → `UNIQUE(tenant_id, deployment_id)` becomes `UNIQUE(tenant_id, source, deployment_id)`. GitHub deployment IDs and release IDs are separate numeric ID spaces; with both stored in one column, a collision would make a real deployment look like a duplicate and silently drop it. Adding `source` to the constraint removes the possibility entirely.
6. **Release-mode repositories need no environment** → the three `setup_required` gates become source-aware: the production-environment requirement applies only when `deployment_source == 'deployment'`. A published release *is* a production ship; there is nothing to classify. Without this, switching to releases would record deployments the dashboard then refuses to show — the exact failure this RFC exists to fix.
7. **`environment_name = "release"` for release-sourced rows** → the column is `NOT NULL` and is surfaced in the deployments list and its environment filter. A fixed, honest label is better than an empty string (looks like a bug) or the tag name (an environment filter that lists every version ever shipped). The tag goes in `ref`, where it belongs.
8. **`published_at` is the deployment time** → `deployed_at = completed_at = published_at`, `started_at = created_at` (the release's creation, i.e. when the draft or tag was made). Falling back to `created_at` if `published_at` is absent. Publication is the moment the team shipped.
9. **No tag → SHA resolution in v1** → the release payload carries `target_commitish` (a branch name *or* a SHA), not the tag's commit. `commit_sha` is stored only when `target_commitish` is a 40-character hex SHA, otherwise empty. Nothing reads `commit_sha`: attribution is time-window based, and no metric touches it. Resolving the tag would need a second GitHub API call per release for a field no one reads.
10. **`release.published` only, drafts and pre-releases excluded** → `published` is the only action that reliably marks "this shipped". `created` is explicitly rejected: GitHub fires it when a **draft is saved**, and does *not* fire it when that draft is later published, so every draft-first workflow (release-drafter, semantic-release, or simply reviewing before publishing) would record a deployment at draft time and nothing at ship time. `published` fires whenever a release goes live, including one promoted from a draft. A pre-release promoted to GA fires `release.released`, which v1 does not handle; it is a small, additive follow-up if teams ask for it.
11. **Owner-only mutation via `PATCH /repos/{repo_id}`** → matches the existing destructive/administrative model (`require_owner` on add, remove, unlink). The setting changes what the whole workspace's numbers mean.
12. **No backfill, no recomputation on switch** → consistent with deployment tracking, which has never imported history. Switching takes effect from the next matching event; nothing is deleted or recomputed.

---

## Data Model Changes

### `repositories`

| Column              | Type          | Null | Default        | Notes                              |
| ------------------- | ------------- | ---- | -------------- | ---------------------------------- |
| `deployment_source` | `VARCHAR(20)` | no   | `'deployment'` | `'deployment'` \| `'release'`      |

Constrained in the application layer (a `Literal` in the schema, a check in the service). No DB enum: adding a third source later should not need a type migration.

### `deployment_events`

| Column   | Type          | Null | Default        | Notes                         |
| -------- | ------------- | ---- | -------------- | ----------------------------- |
| `source` | `VARCHAR(20)` | no   | `'deployment'` | What produced this row        |

Existing rows backfill to `'deployment'` via the server default.

The unique constraint changes:

```
DROP  UNIQUE (tenant_id, deployment_id)
CREATE UNIQUE (tenant_id, source, deployment_id)
```

### Field mapping for a release

| `deployment_events` column | Release payload                                                    |
| -------------------------- | ------------------------------------------------------------------- |
| `deployment_id`            | `release.id`                                                        |
| `environment_name`         | `"release"` (constant)                                              |
| `ref`                      | `release.tag_name`                                                  |
| `commit_sha`               | `release.target_commitish` when it is a 40-hex SHA, else `""`       |
| `started_at`               | `release.created_at`                                                |
| `completed_at`             | `release.published_at` (fallback `created_at`)                      |
| `deployed_at`              | same as `completed_at`                                              |
| `html_url`                 | `validate_github_url(release.html_url)`                             |
| `source`                   | `"release"`                                                         |

### Migration

One Alembic revision on head `b2c3d4e5f6a7`:

1. `ADD COLUMN repositories.deployment_source` with server default `'deployment'`, `NOT NULL`.
2. `ADD COLUMN deployment_events.source` with server default `'deployment'`, `NOT NULL`.
3. Drop the old `(tenant_id, deployment_id)` unique constraint; create `uq_deployment_events_tenant_source_deployment` on `(tenant_id, source, deployment_id)`.

Downgrade reverses all three (the constraint reverts to `(tenant_id, deployment_id)` — safe, since a downgrade implies no release rows are wanted; the migration drops release-sourced rows first so the narrower constraint can be created).

---

## Architecture

### Ingest

```
release webhook ─┐
                 ├─→ dispatcher → handler → fan-out over Repository rows
deployment_status┘                            ├─ filter: repo.deployment_source == handler's source
                                              ├─ (deployment only) environment must be production
                                              └─ INSERT deployment_events … ON CONFLICT DO NOTHING
                                                 └─ attribute_prs_to_deployment(…)
```

A new `server/app/services/ingest_release_service.py` mirrors the shape of `ingest_deployment_service.py`:

```python
RELEASE_ENVIRONMENT_NAME = "release"

@register_handler("release")
async def handle_release_event(payload: dict, session: AsyncSession) -> str | None:
    if payload.get("action") != "published":
        return SKIPPED
    release = payload["release"]
    if release.get("draft") or release.get("prerelease"):
        return SKIPPED
    # fan out over Repository rows for payload["repository"]["id"]
    # skip any repo whose deployment_source != "release" (logged, not silent)
    # insert + attribute, exactly as the deployment path does
```

`handle_deployment_status_event` gains the mirror-image filter: a repository whose `deployment_source` is `'release'` is skipped with a log line before the environment lookup, so release-mode repos never produce `environment_unknown` warnings.

Both handlers return `SKIPPED` when no repository was handled, so a delivery that matched nothing shows as `skipped` in `webhook_events` (per `docs/runbooks/webhook-redelivery.md`).

Registration: `main.py` imports the new service module alongside the existing ingest services.

### Read path

`read_metrics_service` gets one helper:

```python
def requires_production_environment(repo: Repository) -> bool:
    return repo.deployment_source == "deployment"
```

used by `get_deployment_frequency_section`, `get_lead_time_section` and `get_pr_cycle_time_section` to decide whether to run the `get_production_environments` gate at all. `get_data_quality_section` keeps reporting `has_production_environment` truthfully and gains `deployment_source` in `SetupInfo`, so the client can stop nagging release-mode repos about environments.

Nothing else on the read path changes. `compute_deployment_frequency` and `compute_lead_time` already select every `deployment_events` row for the repo, which is exactly the desired behaviour.

---

## Backend Changes

| File                                            | Change                                                                                     |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `app/models/repository.py`                      | `deployment_source` column                                                                   |
| `app/models/deployment_event.py`                | `source` column; unique constraint now `(tenant_id, source, deployment_id)`                  |
| `database/versions/<rev>_deployment_source.py`  | New migration (above)                                                                        |
| `app/services/ingest_release_service.py`        | **New** — `release` handler                                                                  |
| `app/services/ingest_deployment_service.py`     | Skip repositories in release mode                                                            |
| `app/services/read_metrics_service.py`          | Source-aware `setup_required` gates; `deployment_source` in the data-quality setup block     |
| `app/schemas/metrics.py`                        | `SetupInfo.deployment_source`                                                                |
| `app/schemas/repos.py`                          | `RepoResponse.deployment_source`; new `UpdateRepoRequest`                                    |
| `app/routes/repos.py`                           | `PATCH /repos/{repo_id}` (owner-only)                                                        |
| `app/schemas/deployments.py`                    | `DeploymentResponse.source`                                                                  |
| `app/main.py`                                   | Import the new ingest service so its handler registers                                       |

### `PATCH /repos/{repo_id}`

```
PATCH /repos/{repo_id}
{ "deployment_source": "release" }
→ 200 RepoResponse
→ 403 not an owner
→ 404 repo not in this workspace (or soft-removed)
→ 422 invalid source
```

Scoped to `current.tenant_id`, so one workspace cannot retarget another's repository row.

---

## Frontend Changes

| File                                                      | Change                                                                       |
| --------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `src/components/settings/DeploymentTrackingPage.tsx`       | **New** — settings page, repo list, per-repo source control                    |
| `src/components/ProfileMenu.tsx`                           | New owner-only "Deployment Tracking" entry                                     |
| `src/App.tsx`                                              | `settingsPage` union gains `"deployments"`                                     |
| `src/components/Dashboard.tsx`                             | Pass `onOpenDeploymentTracking` through to `ProfileMenu`                       |
| `src/types/dashboard.ts`                                   | `Repo.deployment_source`; `DataQualitySetup.deployment_source`                 |
| Components reading `has_production_environment`            | Suppress environment guidance for release-mode repos                           |

### The page

Follows `RepositoriesPage` exactly: `max-w-3xl`, `Settings · Deployment Tracking` header, "Back to dashboard", a `Card` per repository. Each row: full name on the left, a two-button segmented control (**Deployments** / **Releases**) on the right, saving on click via `PATCH` and rolling back the displayed value if the request fails.

One short paragraph at the top states what the choice means, that it applies from the next event, and that release tracking requires the updated GitHub App permission to have been accepted.

Design: dark surfaces, no decorative colour — the selected segment uses the existing `primary` treatment, the unselected one `muted-foreground`, consistent with `DashboardControls`.

---

## Documentation

| File                                  | Change                                                                          |
| ------------------------------------- | -------------------------------------------------------------------------------- |
| `docs/adrs/011-release-tracking-permission.md` | **New** — why Contents: read is now requested, what it costs, what was rejected |
| `docs/github-app.md`                  | `release` event row; Contents: read in the permission table with its justification; the "deliberately not requested" list loses Contents |
| `docs/architecture.md`                | Ingest services list, the deployment flow, and the per-repo source              |
| `docs/metrics.md`                     | Both definitions of a deployment                                                 |
| `docs/runbooks/local-setup.md`        | Permission table; how to test a release event locally                            |
| `docs/runbooks/webhook-redelivery.md` | `release` in the event-type queries and the skipped-delivery notes               |
| `README.md`, `server/README.md`, `client/README.md` | Feature mention where deployment tracking is described               |

---

## Test Strategy

Red/green TDD throughout. New and changed behaviour only — no rewriting of existing passing tests beyond the two fixtures that gain a column.

### `server/tests/test_ingest_release_service.py` (new)

- `release.published` on a release-mode repo → one `deployment_events` row with the mapped fields.
- Draft release → no row, handler returns `SKIPPED`.
- Pre-release → no row, `SKIPPED`.
- Action other than `published` (`created`, `edited`, `deleted`) → `SKIPPED`.
- Repo in `deployment` mode → no row, `SKIPPED`.
- Unknown `github_id` → `SKIPPED`.
- Redelivery of the same release → one row, no error.
- Two workspaces tracking the repo, one in each mode → exactly one row, for the release-mode workspace.
- PRs merged since the previous deployment are attributed to the release-sourced row.
- `target_commitish` as a branch name → `commit_sha == ""`; as a 40-hex SHA → stored.
- `html_url` from a non-github.com host → stored empty (`validate_github_url`).

### `server/tests/test_ingest_deployment_service.py` (extended)

- Successful `deployment_status` on a release-mode repo → no row, `SKIPPED`.
- Existing deployment-mode behaviour unchanged.

### `server/tests/test_repos.py` (extended)

- Owner PATCHes `deployment_source` → 200, persisted, echoed in `GET /repos`.
- Member PATCHes → 403.
- Invalid value → 422.
- Repo in another workspace → 404.
- Default on a newly added repo is `deployment`.

### `server/tests/test_read_metrics_service.py` / `test_metrics_routes.py` (extended)

- Release-mode repo with no environments → deployment frequency, lead time and PR cycle time all return `status="ok"`.
- Deployment-mode repo with no production environment → still `setup_required`.
- Data quality reports `deployment_source`.

### Client

- `DeploymentTrackingPage.test.tsx` (new): renders a row per repo with the current source selected; clicking the other option issues the PATCH and reflects the new value; a failed PATCH restores the previous value and shows an error.
- `ProfileMenu.test.tsx` (extended): the entry shows for owners, not for members.

### Manual verification

Against the local stack (`docs/runbooks/local-setup.md`): switch a repo to releases, send a signed `release.published` payload, confirm the row, the dashboard count, and the `webhook_events` outcome; then send a `deployment_status` for the same repo and confirm it is recorded as `skipped`.

---

## Risks & Open Questions

1. **Contents: read on every installation** *(known cost, accepted)* — existing installations must approve the new permission before any release event is delivered. Mitigations: the settings page says so plainly; the ADR records the trade-off; `docs/github-app.md` states exactly what the permission is used for (event delivery only — no Contents API call exists in the codebase, and none is added here).
2. **A release-mode repo with no events looks identical to a quiet repo** — an owner who switches before approving the permission sees nothing and has no signal why. v1 warns on the settings page. A follow-up could surface "no release seen since you switched" in the data-quality section.
3. **Teams that both deploy and release** pick one and under-count the other. This is the intended behaviour (PRD non-goal), but it is the most likely source of "my numbers look low" support questions.
4. **`environment_name = "release"`** shows in the deployments list's environment filter as a pseudo-environment. Honest, but slightly odd if a repo has both historic deployment rows and new release rows. Accepted; the alternative (nullable column) touches more of the read path than it is worth.
5. **Pre-release promotion (`release.released`)** is unhandled. If teams ship RC → GA this way, their GA ship is missed entirely. Cheap to add once someone asks.

---

## Out of Scope

- Backfilling releases from the GitHub API.
- `release.released`, `release.edited`, `release.deleted`.
- Tag-push tracking, workflow-run tracking, or any non-GitHub deployment source.
- A workspace-level default that new repositories inherit.
- Recomputing or migrating history when a source changes.
- Surfacing per-source breakdowns in metrics or charts.
