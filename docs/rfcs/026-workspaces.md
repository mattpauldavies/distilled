# RFC 026: Workspaces — Rename, Creation, and Repository Management

## Summary

Rename tenants to **workspaces** across the product, and turn them into something users can have several of. First login provisions a workspace named **"My Workspace"** instead of one named after the GitHub username. Users can create additional workspaces, connect GitHub App installations to them, choose which repositories each workspace tracks, remove repositories from one workspace and add them to another, and two users can track the same repository in their own private workspaces.

The four pillars:

1. **Rename** — "workspace" becomes the product-facing term (UI copy, API routes, headers, docs). The database schema keeps its existing `tenant` names; no table renames.
2. **Creation** — an explicit `POST /workspaces` endpoint and a "Create workspace" flow in the switcher, alongside the existing first-login auto-provisioning.
3. **Installation decoupling** — `github_installations` becomes a global record of the App's installations; a new `tenant_installations` join table connects installations to workspaces many-to-many. Installations are bound to workspaces through an explicit, user-initiated **installation intent** rather than inferred from webhook payloads.
4. **Repository membership** — each workspace curates its own repository set. The same GitHub repository can exist as independent `repositories` rows in any number of workspaces, and webhook ingest fans out to all of them.

A workspace is not a GitHub organisation: one workspace can hold repositories from several installations across several orgs and personal accounts.

---

## Context

Today (post RFCs 016, 021, 023):

- `server/app/services/user_service.py:93-98` — first login creates a `Tenant` named after the GitHub username, with `slug = github_username` (globally unique, never updated). There is **no other way to create a tenant** — the only path to a second membership is accepting an invitation.
- `server/app/routes/team.py:79` — `PATCH /team` already renames a tenant; `client/src/components/team/TeamPage.tsx` has the inline rename UI. The first-invite rename prompt detects a default name by `name === slug` (`client/src/components/team/InviteMemberModal.tsx:34`).
- `server/app/models/tenant_user.py` — membership is many-to-many with an `owner`/`member` role and a DB-enforced one-owner-per-tenant partial index. Active tenant is resolved per request from the `X-Tenant-Id` header with `last_active_tenant_id` fallback (`server/app/auth.py:43-67`).
- `client/src/components/OnboardingScreen.tsx:6-7` — the install link is `https://github.com/apps/<slug>/installations/new` with **no state parameter**. There is no setup callback; the target tenant is inferred server-side.
- `server/app/services/ingest_installation_service.py:59-92` — `installation.created` matches `installation.account.id` against `users.github_account_id`, then picks an owned tenant with `.limit(1)` and **no ordering**. Two consequences: organisation installs are silently skipped (an org's account id never matches a user row), and once a user owns two workspaces the target is non-deterministic.
- Three ingest lookups assume global uniqueness and use `scalar_one_or_none()`: `_get_installation` (`ingest_installation_service.py:52-56`), the repo lookup in `ingest_pr_service.py:40-47`, and its twin in `ingest_deployment_service.py:25-32`. Any duplicate across tenants raises `MultipleResultsFound` and permanently fails those deliveries — for **every** tenant involved.
- `server/app/models/repository.py:12` — `UNIQUE(tenant_id, github_id)`: the schema already permits the same repo in two tenants; only the ingest code forbids it.
- There is no repo-removal API and no repo picker: repos appear and disappear solely via `installation` / `installation_repositories` webhooks (RFC 023 soft delete).
- `GitHubClient.list_repos` (`server/app/services/github_client.py:199-215`) is implemented and tested but has no production caller.

### The GitHub constraint

A GitHub App can be installed **at most once per GitHub account** (user or organisation). Two Distilled users who both want `acme/api` in their private workspaces cannot create two installations on `acme` — they necessarily share one. "Separate installations" only happens when the repositories live under different GitHub accounts (e.g. each user's fork, or repos in different orgs). The design therefore treats installations as shared, global resources that any number of workspaces can attach to, with per-workspace repository rows keeping the data private to each workspace.

---

## Decisions

1. **Rename depth** → product surfaces only. UI copy, client code, API routes (`/workspaces`, `/me/workspaces`, `/me/active-workspace`), the `X-Workspace-Id` header, JSON field names, and docs all say "workspace". The **database schema keeps `tenants` / `tenant_users` / `tenant_id`**, and existing server modules keep their identifiers; new DB objects follow the existing `tenant_*` convention (`tenant_installations`). `docs/architecture.md` records the equivalence ("workspace" in the product = `tenant` in the schema). Rationale: a full schema-and-code rename is ~2,500 mechanical touches and a table-rename migration with zero behaviour change — high regression risk for cosmetic benefit, and contrary to this project's minimal-impact principle. A follow-up internal rename can be its own RFC if the seam proves annoying.
2. **Default workspace name** → `"My Workspace"`. First-login provisioning stops deriving the name from the GitHub username and stops writing `slug` (new workspaces get `slug = NULL`, which sidesteps the global-unique slug collision a second workspace would cause). `slug` is deprecated: kept for existing rows, never written again. Existing workspaces keep their current names — no backfill rename.
3. **Default-name detection** → server-computed. `GET /team` gains `is_default_name`, true when `name == "My Workspace"` or (legacy) `slug IS NOT NULL AND name == slug`. The client stops comparing `name === slug`.
4. **Installation ↔ workspace binding** → explicit intent, never inference. Connecting GitHub to a workspace mints an **installation intent** (workspace, user, nonce, TTL); the install URL carries the nonce as GitHub's `state` parameter. Binding happens through two redundant mechanisms (§Architecture): the GitHub **Setup URL callback** (primary) and **webhook sender matching** against open intents (fallback). The legacy `account.id → users.github_account_id → .limit(1)` heuristic is deleted — which also fixes the silently-broken organisation-install path.
5. **Installations are global, links are per-workspace** → `github_installations` drops `tenant_id` and becomes unique on `installation_id`; a new `tenant_installations` join table records which workspaces use which installation. Uninstalling the App on GitHub soft-deletes the global row; unlinking from one workspace only removes that workspace's link and soft-deletes its repos.
6. **Repositories stay per-workspace rows; ingest fans out** → the existing `repositories` `UNIQUE(tenant_id, github_id)` shape is kept. The same GitHub repo in three workspaces is three `Repository` rows, each with its own environments, PRs, deployments, and metrics. The three `scalar_one_or_none()` global lookups become fan-out loops over all matching rows. This preserves the tenant-scoped data model, cascade deletion, and read paths untouched, at the cost of duplicated ingest rows — acceptable at current scale and revisitable behind the same service seams.
7. **Repo membership is curated, removals are sticky** → binding an installation to a workspace auto-adds all repos currently granted to it (the user just chose them on GitHub's install screen). Afterwards: repos newly granted to the installation (`installation_repositories.added`) are auto-added to every linked workspace **except** where that workspace previously removed the repo (`removed_at` set) — webhook syncs never resurrect a deliberate removal. Explicit user adds always resurrect. Removal from a workspace is the existing soft delete, now exposed as `DELETE /repos/{id}`.
8. **Repo add/remove permissions** → owner-only, matching the existing destructive-action model (`require_owner`). Members inherit visibility as today.
9. **Available-repos listing is live, not cached** → the "add repositories" picker queries GitHub via the installation token (`GitHubClient.list_repos`, finally wired in) rather than maintaining a repo catalogue table. No new staleness surface, no reconciliation job.
10. **Header and route migration** → the server accepts `X-Workspace-Id` and falls back to `X-Tenant-Id` (kept indefinitely — one line); the client sends `X-Workspace-Id`. Renamed routes get no aliases: the SPA is the only consumer, deploys are coordinated, and a stale tab recovers on refresh.

---

## Concepts

### Workspace

The unit of data isolation and membership — the renamed tenant. Everything RFC 021 built (owner/member roles, invitations, switcher, rename, sole-user deletion) carries over unchanged. New: any user can create additional workspaces (becoming their owner), so "one user owns several workspaces" is now a normal state.

### Installation

A global record of the GitHub App installed on one GitHub account. Not owned by any workspace. Carries `account_login`, `account_type`, and soft-delete state mirroring GitHub. Workspaces attach to it via links.

### Installation link (`tenant_installations`)

A workspace's claim on an installation: "this workspace may track repos granted to this installation". Created only through the intent flow. Deleting a link detaches the workspace (soft-deleting its repos from that installation) without touching the installation or other workspaces.

### Installation intent

A short-lived, single-use token binding "user U wants to connect an installation to workspace W". Minted server-side before redirecting to GitHub; consumed by the setup callback or by webhook sender matching. Intents expire (default 30 minutes) and are superseded by newer intents from the same user.

### Repository membership

A `repositories` row means "workspace W tracks GitHub repo R via installation I". Rows are independent across workspaces: soft-deleting one workspace's row does not affect another's, and each row accumulates its own ingested history.

---

## Data Model Changes

### Modified: `github_installations` — globalised

```sql
-- after de-dup backfill (see Migration):
ALTER TABLE github_installations DROP COLUMN tenant_id;
ALTER TABLE github_installations ADD CONSTRAINT uq_github_installations_installation_id
    UNIQUE (installation_id);
```

`removed_at` now means "the App was uninstalled from this GitHub account" — a global fact.

### New: `tenant_installations`

```python
class TenantInstallation(TimestampMixin, Base):
    __tablename__ = "tenant_installations"

    id: UUID PK
    tenant_id: UUID FK → tenants.id ON DELETE CASCADE
    github_installation_id: UUID FK → github_installations.id ON DELETE CASCADE

    __table_args__ = (
        UniqueConstraint("tenant_id", "github_installation_id",
                         name="uq_tenant_installations_tenant_installation"),
    )
```

### New: `installation_intents`

```python
class InstallationIntent(TimestampMixin, Base):
    __tablename__ = "installation_intents"

    id: UUID PK
    tenant_id: UUID FK → tenants.id ON DELETE CASCADE
    user_id: UUID FK → users.id ON DELETE CASCADE
    nonce_hash: TEXT NOT NULL UNIQUE     # SHA-256 of the state token (same pattern as invitations)
    expires_at: TIMESTAMPTZ NOT NULL
    consumed_at: TIMESTAMPTZ NULL
```

At most one open intent per user: creating a new intent expires any previous open ones for that user (simple `UPDATE`, not a constraint). This keeps webhook sender matching unambiguous.

### Modified: `tenants`

No schema change. `slug` is deprecated in behaviour: never written for new workspaces, never read except by legacy default-name detection.

### Unchanged: `repositories`

Keeps `tenant_id`, `installation_id` (FK to `github_installations.id`), `github_id`, `removed_at`, and `UNIQUE(tenant_id, github_id)`. The FK to the now-global installation row remains valid.

### Migration

A single Alembic revision:

1. Create `tenant_installations`; backfill one link per existing `github_installations` row: `INSERT INTO tenant_installations (id, tenant_id, github_installation_id) SELECT gen_random_uuid(), tenant_id, id FROM github_installations;`
2. Defensively de-duplicate `github_installations` on `installation_id` (the current code cannot create duplicates, but the schema allowed it): keep the oldest row per `installation_id`, repoint `repositories.installation_id` and `tenant_installations.github_installation_id` at the survivor, delete the rest.
3. Drop `github_installations.tenant_id`; add the unique constraint on `installation_id`.
4. Create `installation_intents`.

No data loss, no behaviour change for existing single-workspace users: their installation is linked to the same workspace it lived in.

---

## Architecture

### First login (changed naming only)

`get_or_create_user` provisions `Tenant(name="My Workspace", slug=None)` + `User` + owner membership, exactly as today otherwise.

### Creating a workspace

```
Client                              FastAPI
  │── POST /workspaces {name} ──────►│  require_user (JWT only, no workspace scope)
  │                                  │  create Tenant + TenantUser(owner)
  │                                  │  set users.last_active_tenant_id
  │◄── 201 {id, name, role} ─────────│
  │  switcher refreshes, activates the new workspace
```

The new workspace has no installations and no repos, so the client lands on the onboarding screen for it.

### Connecting GitHub to a workspace (the intent flow)

```
Client                         FastAPI                        GitHub
  │── POST /installations/intents ─►│ require_owner
  │                                 │ expire user's open intents
  │                                 │ create intent, return raw nonce
  │◄─ {install_url} ────────────────│   (…/installations/new?state=<nonce>)
  │── browser → GitHub install/configure screen ─────────────────►│
  │                                                               │
  │   [A] Setup URL redirect: /github/setup?installation_id=…&setup_action=…&state=<nonce>
  │◄──────────────────────────────────────────────────────────────│
  │── POST /installations/claim {installation_id, state} ─►│
  │                                 │ validate nonce (hash, TTL, unconsumed, owner of intent's workspace)
  │                                 │ upsert global installation (fetch details via app JWT if webhook hasn't arrived)
  │                                 │ link tenant_installations; consume intent
  │                                 │ sync all granted repos into the workspace; discover environments
  │◄─ 200 {workspace_id} ───────────│ client switches to that workspace
  │
  │   [B] Webhook (fallback / race): installation.created or installation_repositories.*
  │                                 │ sender.id → users.github_account_id → open unexpired intent?
  │                                 │ yes → same bind-and-sync as [A]; consume intent
  │                                 │ no  → upsert global installation only (unclaimed; no repos anywhere)
```

Mechanisms [A] and [B] are idempotent against each other — whichever lands first does the bind; the second finds the intent consumed (or the link already present) and only refreshes installation metadata. This requires two GitHub App settings changes (ops task): set the **Setup URL** to `{APP_BASE_URL}/github/setup` and enable **"Redirect on update"** so re-configuring an existing installation also returns the user to us. Deleted entirely: the `account.id → owner-tenant` heuristic.

**Sharing an installation** (two users, same org): the second user runs the same intent flow from their own workspace. GitHub shows them the existing installation's configure screen; saving it fires the Setup URL redirect (and usually an `installation_repositories` webhook), either of which claims their intent and adds a second `tenant_installations` link. Each workspace then holds its own `repositories` rows for whichever repos its owner adds.

### Ingest fan-out

The three global lookups change shape:

- `_get_installation` — unchanged semantics, now guaranteed unique by the new constraint.
- `ingest_pr_service` / `ingest_deployment_service` — `select(Repository).where(github_id == …)` returns **all** rows; the handler loops, ingesting one event into each workspace's row (each with its own tenant-scoped environments, attribution, and unique constraints). Zero rows → skip as today.
- `installation_repositories.added` — upsert repos into every linked workspace, skipping rows where `removed_at IS NOT NULL` (sticky removals). `removed` — stamp `removed_at` across all linked workspaces' matching rows.
- `installation.deleted` — stamp the global installation and all linked workspaces' repos; links are kept so a re-install resurrects cleanly (webhook resync respects sticky removals; the intent-claim path resurrects everything, because it is an explicit user action).

### Managing a workspace's repositories

New owner-only settings surface (§Frontend). Flows:

- **Remove**: `DELETE /repos/{repo_id}` → soft delete in this workspace only. Historical data retained per RFC 023; the repo disappears from `GET /repos` and stops being auto-re-added by webhooks.
- **Add**: `GET /installations` lists the workspace's linked installations; `GET /installations/{installation_id}/available-repos` calls GitHub live (installation token) and annotates each repo with whether the workspace already tracks it; `POST /repos {installation_id, github_ids}` validates the repos against that live list, upserts rows (clearing `removed_at`), and discovers environments.
- **Move between workspaces**: composition of the above — remove in workspace A; in workspace B, link the installation (intent flow, once) and add the repo. No dedicated "move" endpoint; history stays with A's soft-deleted row, and B starts accumulating its own from that point.
- **Unlink an installation**: `DELETE /installations/{installation_id}` removes this workspace's link and soft-deletes its repos from that installation.

### Request scoping

`_resolve_active_tenant` reads `X-Workspace-Id` first, then `X-Tenant-Id`, then `last_active_tenant_id` — otherwise unchanged (403 non-member, 409 none). CORS `allow_headers` gains `X-Workspace-Id`.

---

## Backend Changes

### 1. Models

- Modify `github_installation.py` (drop `tenant_id`, unique `installation_id`); new `tenant_installation.py`, `installation_intent.py`; export from `models/__init__.py`.

### 2. `app/services/user_service.py`

- Provision `name="My Workspace"`, `slug=None`.
- New `create_workspace(user_id, name, session) -> Tenant` — creates tenant + owner membership + sets `last_active_tenant_id` (shared by first-login provisioning and `POST /workspaces`).

### 3. New: `app/services/installation_link_service.py`

The intent/claim/link lifecycle, kept separate from webhook ingest:

```python
async def create_intent(tenant_id, user_id, session) -> str            # returns raw nonce
async def claim_intent(nonce, installation_id, user_id, session) -> Tenant   # mechanism [A]
async def claim_by_sender(github_account_id, installation_id, session) -> bool  # mechanism [B]
async def bind_installation(tenant_id, installation_id, session) -> None     # shared: link + full repo sync + env discovery
async def list_workspace_installations(tenant_id, session) -> list[...]
async def unlink_installation(tenant_id, installation_id, session) -> None
async def list_available_repos(tenant_id, installation_id, session) -> list[...]  # live via GitHubClient.list_repos
async def add_repos(tenant_id, installation_id, github_ids, session) -> list[Repository]
async def remove_repo(tenant_id, repo_id, session) -> None
```

`claim_intent` fetches installation details via app JWT (`GET /app/installations/{id}`) when the webhook hasn't arrived yet, and verifies the intent belongs to the claiming user and an owned workspace.

### 4. `app/services/ingest_installation_service.py`

- `_handle_created`: delete the account-matching heuristic. Upsert the global installation; call `claim_by_sender(sender.id, …)`; if no intent matched, stop (unclaimed installation, warning log).
- `_handle_repositories_added/removed` and `_handle_deleted`: loop over `tenant_installations` links as per §Ingest fan-out. `sync_repos` gains a `respect_removed: bool` flag (webhook paths `True`, explicit binds/adds `False`). `_handle_repositories_*` also attempt `claim_by_sender` first, so a configure-only visit that fires no redirect can still claim.

### 5. `app/services/ingest_pr_service.py` / `ingest_deployment_service.py`

Replace `scalar_one_or_none()` with `.scalars().all()` and loop. The `# globally unique` comments go.

### 6. Routes

New `app/routes/workspaces.py` and `app/routes/installations.py`:

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/workspaces` | Create workspace `{name}` | `require_user` (JWT only) |
| POST | `/installations/intents` | Mint intent; returns `{install_url}` | `require_owner` |
| POST | `/installations/claim` | `{installation_id, state}` → bind (mechanism [A]) | `require_user` |
| GET | `/installations` | Linked installations for active workspace | `require_auth` |
| GET | `/installations/{installation_id}/available-repos` | Live grant list, annotated | `require_owner` |
| POST | `/repos` | `{installation_id, github_ids}` add to active workspace | `require_owner` |
| DELETE | `/repos/{repo_id}` | Soft-remove from active workspace | `require_owner` |
| DELETE | `/installations/{installation_id}` | Unlink from active workspace | `require_owner` |

Renamed: `GET /me/tenants` → `GET /me/workspaces`; `POST /me/active-tenant` → `POST /me/active-workspace`. `/team/*` paths are unchanged (nothing tenant-named in them); `GET /team`'s response field `tenant` becomes `workspace` and gains `is_default_name`.

### 7. `app/auth.py`, `app/main.py`

Header fallback chain (`X-Workspace-Id` → `X-Tenant-Id`); CORS header addition; register the new routers.

### 8. Targeted fix (in scope because fan-out multiplies its cost)

`GET /internal/metrics/recompute-targets` (`app/routes/internal.py:90`) gains a `removed_at IS NULL` filter so soft-deleted repos stop consuming hourly recompute budget.

### 9. Error copy

User-facing strings in team/invitation/auth responses that say "tenant" switch to "workspace".

---

## Frontend Changes

### 1. Terminology rename

Full client-side rename (~166 occurrences): types (`TenantSummary` → `WorkspaceSummary`), context (`tenantContext.tsx` → `workspaceContext.tsx`), copy ("Switch Tenant" → "Switch workspace", "Delete tenant" → "Delete workspace", invite email subject line, etc.). `localStorage` key becomes `distilled.activeWorkspaceId`, reading the old key once as a fallback on first load.

### 2. Create workspace

`ProfileMenu` gains a **Create workspace** item beneath the membership list → small modal (name field, pre-filled empty, placeholder "e.g. Acme Engineering") → `POST /workspaces` → switch to it → onboarding screen for the empty workspace.

### 3. Onboarding screen

- Requests an intent (`POST /installations/intents`) and uses the returned `install_url` instead of the static env-built link.
- The repo poll uses `useApiFetch` so it carries `X-Workspace-Id` — fixing the existing bug where the poll resolves against `last_active_tenant_id` rather than the workspace on screen.
- Copy updated: installing connects repos "to this workspace".

### 4. New: setup callback page

`/github/setup` route (alongside the existing `/invitations/accept` special case): reads `installation_id`/`setup_action`/`state` from the query string, POSTs `/installations/claim`, switches to the bound workspace, redirects to `/` with a success toast. Signed-out visitors see the Clerk sign-in with a redirect back, mirroring `AcceptInvitePage`.

### 5. New: Settings → Repositories

Owner-only page beside Team:

```
┌──────────────────────────────────────────────────────────┐
│  Repositories                        [Add repositories]  │
│  ──────────────────────────────────────────────────────  │
│  acme/api            via acme (org)              [✕]     │
│  acme/web            via acme (org)              [✕]     │
│  matt/side-project   via mattd (user)            [✕]     │
│                                                          │
│  Connected GitHub accounts                               │
│  ──────────────────────────────────────────────────────  │
│  acme (organisation)   2 repos tracked      [Unlink]     │
│  mattd (user)          1 repo tracked       [Unlink]     │
│                                    [+ Connect GitHub]    │
└──────────────────────────────────────────────────────────┘
```

"Add repositories" opens a picker listing each linked installation's available repos (live) with checkboxes for the untracked ones. "Connect GitHub" runs the intent flow. Remove and Unlink get confirmation dialogs stating that historical data is retained but hidden.

### 6. Default-name prompt

`InviteMemberModal` switches from `name === slug` to the server's `is_default_name`.

---

## Documentation

- `docs/architecture.md` — rewrite the Multi-tenancy section as "Workspaces (tenants in the schema)": the naming equivalence, installation globalisation, intent binding, ingest fan-out.
- `docs/adrs/` — new ADR: product rename without schema rename + installations as global shared resources.
- `docs/getting-started.md` — creating workspaces, connecting GitHub, managing repos, moving a repo between workspaces.
- `README.md` / `server/README.md` / `client/README.md` — terminology sweep; GitHub App setup instructions gain the Setup URL + "Redirect on update" configuration.
- `docs/runbooks/webhook-redelivery.md` — note the fan-out semantics and unclaimed-installation logs.

---

## Test Strategy

### Backend

- `test_user_service.py` — provisioning names "My Workspace" with `slug=None`; `create_workspace` creates owner membership and sets last-active; a user owning several workspaces resolves correctly.
- `test_installation_link_service.py` (new) — intent mint/expiry/supersession; claim happy path; claim with expired/consumed/foreign nonce → 4xx; claim before webhook (app-JWT fetch mocked); `claim_by_sender` matches only open unexpired intents; bind syncs repos + environments; unlink soft-deletes only that workspace's repos; `add_repos` validates against the live grant list and resurrects; `remove_repo` sticky semantics.
- `test_ingest_installation_service.py` — rewrite tenant-matching tests around intents: `created` with matching sender claims; without → unclaimed, no repos; org-account install with intent now works (regression test for the previously-masked org bug); `repositories.added` fans out to all links and skips sticky removals; `deleted` stamps globally; duplicate-installation `MultipleResultsFound` scenario now impossible (constraint test).
- `test_ingest_pr_service.py` / `test_ingest_deployment_service.py` — same repo in two workspaces → both rows ingest; zero rows → skip.
- `test_routes_workspaces.py` / `test_routes_installations.py` (new) — endpoint contracts, owner-only enforcement, active-workspace scoping.
- `test_auth.py` — `X-Workspace-Id` honoured; `X-Tenant-Id` fallback still works.
- Migration test — backfilled links match pre-migration `github_installations` rows.

### Frontend

- `workspaceContext` — old localStorage key migration.
- `CreateWorkspaceModal` — create → switch → onboarding for empty workspace.
- `OnboardingScreen` — intent-based URL; poll sends `X-Workspace-Id`.
- `SetupCallbackPage` — signed-out → sign-in with redirect; signed-in → claim → switch + toast; invalid state → error with retry guidance.
- `RepositoriesPage` — add picker (tracked repos disabled), remove confirmation, unlink confirmation.
- `InviteMemberModal` — rename prompt driven by `is_default_name`.

### Seed data

`seed_demo.py` / `claim_seed_data.py` updated: a user owning two workspaces, one shared installation linked to both, one repo present in both workspaces, one sticky-removed repo.

---

## Risks & Open Questions

1. **`state` propagation on the re-configure path.** GitHub documents the `state` parameter for `…/installations/new` and "Redirect on update" for changes to existing installations; whether `state` survives every configure-only round trip is not something we can confirm from docs alone. Mitigation is already designed in: webhook sender matching (mechanism [B]) claims the intent whenever any installation event fires. Residual gap: a second user re-configuring an existing installation while changing nothing may fire neither redirect-with-state nor a webhook — the UI keeps the "waiting" state with guidance to adjust repo selection. To be verified against the real App early in implementation; if `state` proves unreliable we lean fully on [B].
2. **Ingest write amplification.** A repo in N workspaces ingests every PR/deployment event N times and recomputes metrics N times. Fine at current scale; the fan-out loop is the single seam to revisit (shared ingest + read-time scoping) if it becomes a cost problem.
3. **Unclaimed installations are invisible.** Someone installing the App directly from GitHub without an intent gets a global row and nothing else. Acceptable for v1 (warning log + the user can re-run Connect GitHub from a workspace, which claims via [B] on the next event or via a fresh configure round trip).

---

## Out of Scope

- Renaming database tables/columns or existing server-side Python identifiers (Decision 1; possible follow-up RFC).
- Backfill-renaming existing workspaces to "My Workspace".
- Workspace quotas / limits on creation.
- Roles beyond owner/member; per-repo permissions within a workspace.
- Shared-ingest storage (single row per GitHub repo with read-time workspace scoping).
- A dedicated one-click "move repo to another workspace" action (achievable by remove + add).
- Handling `installation.suspend` / `unsuspend` events.
- The `webhook_events.tenant_id` orphan-rows gap (no FK, survives workspace deletion).
- Scheduled reconciliation of repo grants against GitHub (the live available-repos call covers the interactive path).
- Billing, workspace transfer between users, or org-level workspace administration.

---

## Implementation Plan

Red/green TDD throughout. Phase ordering keeps the full suite green at every commit: `github_installations.tenant_id` is load-bearing in ingest code, so migration A only relaxes it to nullable; all code moves onto `tenant_installations` links; migration B (Phase 7) drops the column once nothing references it.

**Branch:** `feat/workspaces` off `main`. Commit per task; no Claude references in commits or the PR (No Promo).

**Commands:** backend `cd server && pytest`, frontend `cd client && npm test`, lint via the repo's `make lint` (or the per-package lint scripts it wraps).

### Phase 1: Additive schema + models

- [ ] **1.1** Alembic migration `workspaces_installation_links` (down_revision: current head `e5f6a7b8c9d0`): create `tenant_installations` (`id` UUID PK; `tenant_id` FK→`tenants.id` ON DELETE CASCADE; `github_installation_id` FK→`github_installations.id` ON DELETE CASCADE; timestamps; `uq_tenant_installations_tenant_installation` UNIQUE(tenant_id, github_installation_id)); backfill `INSERT INTO tenant_installations (id, tenant_id, github_installation_id, created_at, updated_at) SELECT gen_random_uuid(), tenant_id, id, now(), now() FROM github_installations;`; create `installation_intents` (`id` UUID PK; `tenant_id` FK CASCADE; `user_id` FK→`users.id` CASCADE; `nonce_hash` TEXT NOT NULL UNIQUE; `expires_at` TIMESTAMPTZ NOT NULL; `consumed_at` TIMESTAMPTZ NULL; timestamps); `ALTER TABLE github_installations ALTER COLUMN tenant_id DROP NOT NULL`.
- [ ] **1.2** New `app/models/tenant_installation.py` (`TenantInstallation`) and `app/models/installation_intent.py` (`InstallationIntent`) matching 1.1; `github_installation.py` `tenant_id` becomes `Mapped[uuid.UUID | None]`; export both new models from `app/models/__init__.py`.
- [ ] **1.3** Run migration locally (`alembic upgrade head`); verify backfill row counts equal `github_installations` count. Full server suite green. Commit.

### Phase 2: Provisioning rename + workspace creation service

- [ ] **2.1** Failing tests in `tests/test_user_service.py`: first login creates tenant with `name == "My Workspace"` and `slug is None`; new `create_workspace(user_id, name, session)` creates `Tenant(name=name, slug=None)` + `TenantUser(role="owner")` + sets `last_active_tenant_id`; blank/whitespace name raises `ValueError`; a user can own two workspaces (partial one-owner index is per tenant — regression guard).
- [ ] **2.2** Implement in `app/services/user_service.py`: module constant `DEFAULT_WORKSPACE_NAME = "My Workspace"`; provisioning uses it and stops writing `slug`; add `create_workspace` (shared shape with the provisioning transaction). Update any existing tests asserting username-derived names/slugs.
- [ ] **2.3** Failing tests in `tests/test_routes_workspaces.py`: `POST /workspaces {name}` → 201 `{id, name, role: "owner"}` and the caller's `last_active_tenant_id` now points at it; 422 on missing/blank name; 401 unauthenticated. Auth is JWT-only (`require_user` from `app/routes/me.py` — move it to `app/auth.py` if importing across route modules is awkward).
- [ ] **2.4** Implement `app/routes/workspaces.py` (`POST /workspaces`, schema `CreateWorkspaceRequest {name: str, min_length=1, max_length=255}` in `app/schemas/workspace.py`); register router in `app/main.py` (per-route auth like `me`). Suite green. Commit.

### Phase 3: GitHub client additions

- [ ] **3.1** Failing tests in `tests/test_github_client.py`: `get_installation(installation_id: int) -> dict` calls `GET /app/installations/{id}` with the app JWT (same auth path as token minting) and returns the payload; raises the client's existing error type on 404.
- [ ] **3.2** Implement in `app/services/github_client.py`. Suite green. Commit.

### Phase 4: Installation link service (intents, claims, repo management)

- [ ] **4.1** Failing tests in `tests/test_installation_link_service.py` (new), covering:
  - `create_intent(tenant_id, user_id, session) -> str`: returns a raw `secrets.token_urlsafe(32)` nonce; stores SHA-256 only; expiry `now + settings.installation_intent_ttl_minutes` (config default 30); creating a second intent for the same user marks earlier open intents consumed (supersession).
  - `claim_intent(nonce, installation_id, user_id, session) -> Tenant`: happy path binds and consumes; expired / consumed / unknown nonce → `IntentError`; nonce belonging to a different user → `IntentError`; installation row absent → fetched via `GitHubClient.get_installation` (mocked) then bound.
  - `claim_by_sender(github_account_id, installation_id, session) -> bool`: matches the open, unexpired intent of the user with that `github_account_id`, binds, consumes, returns True; no user / no open intent → False, no writes.
  - `bind_installation(tenant_id, installation_id, session) -> GitHubInstallation`: upserts the global installation row (`ON CONFLICT (installation_id) DO UPDATE` — see note below — clearing `removed_at`); idempotently inserts the `tenant_installations` link; syncs all granted repos via `GitHubClient.list_repos` (mocked) with `respect_removed=False`; discovers environments. Calling twice creates no duplicate links.
  - `list_workspace_installations(tenant_id, session)`: installations linked to the workspace with `account_login`, `account_type`, tracked-repo count, `removed_at`.
  - `unlink_installation(tenant_id, installation_id, session)`: deletes the link and stamps `removed_at` on this workspace's repos from that installation; other workspaces' rows untouched.
  - `list_available_repos(tenant_id, installation_id, session)`: 403-style `LinkError` when the workspace holds no link; returns live repos (mocked `list_repos`) each annotated `tracked: bool` (a soft-deleted row counts as untracked).
  - `add_repos(tenant_id, installation_id, github_ids, session) -> list[Repository]`: validates ids against the live grant list (unknown id → `LinkError`); upserts rows clearing `removed_at` (explicit adds resurrect); discovers environments for the added repos.
  - `remove_repo(tenant_id, repo_id, session)`: stamps `removed_at`; unknown/foreign repo → `LinkError`.

  Note on the upsert: until Phase 7 there is no DB unique constraint on `installation_id` alone, so `bind_installation` does select-then-insert/update within the session (the webhook dispatcher and claim endpoints each run serially per event; the residual race window is closed by Phase 7's constraint).
- [ ] **4.2** Implement `app/services/installation_link_service.py` with the signatures above plus exceptions `IntentError(Exception)` and `LinkError(Exception)`; add `installation_intent_ttl_minutes: int = 30` to `app/config.py`. `sync_repos` (in `ingest_installation_service.py`) gains keyword-only `respect_removed: bool` — when True, the per-repo upsert skips rows whose existing `removed_at` is not null (`WHERE repositories.removed_at IS NULL` via `on_conflict_do_update(..., where=...)`). Suite green. Commit.

### Phase 5: Ingest rewrite (fan-out, sender claims, heuristic deletion)

- [ ] **5.1** Failing tests in `tests/test_ingest_installation_service.py` (rewrite the tenant-matching cases):
  - `installation.created` with `sender.id` matching a user holding an open intent → installation bound to the intent's workspace, payload repos synced there, environments discovered. Works when `account.type == "Organization"` and `account.id` is an org id (regression for the previously-masked org bug — sender, not account, drives the claim).
  - `installation.created` with no matching intent → global installation row upserted, **no** links, no repos, warning logged, returns `SKIPPED`.
  - `installation.created` for an installation with existing links (re-install) → `removed_at` cleared on the installation; payload repos re-synced into every linked workspace with `respect_removed=True` (a sticky-removed repo stays removed).
  - `installation_repositories.added` → `claim_by_sender` attempted first; repos upserted into every linked workspace, sticky removals skipped; environments discovered per workspace.
  - `installation_repositories.removed` → `removed_at` stamped on matching repos in every linked workspace.
  - `installation.deleted` → `removed_at` stamped on the installation and on every linked workspace's repos from it; links retained.
- [ ] **5.2** Rewrite `app/services/ingest_installation_service.py`: delete the `account.id → users.github_account_id → owned tenant` block (`_handle_created` lines 62-92); `_handle_created` upserts the global row (no `tenant_id`), calls `installation_link_service.claim_by_sender(payload["sender"]["id"], ...)`, then loops `tenant_installations` links for resync; `_handle_repositories_*` and `_handle_deleted` loop links instead of reading `installation.tenant_id`; `sync_repos` and `_discover_repo_environments` take the link's `tenant_id`. No code path writes `github_installations.tenant_id` any more.
- [ ] **5.3** Failing tests in `tests/test_ingest_pr_service.py` and `tests/test_ingest_deployment_service.py`: the same `github_id` present in two workspaces → the event ingests one row per workspace (each under its own `tenant_id`); zero matching rows → skip unchanged.
- [ ] **5.4** Implement fan-out: both services replace `scalar_one_or_none()` with `.scalars().all()` and loop the existing per-repo logic (including per-workspace attribution for deployments). Delete the `# globally unique` comments. Suite green. Commit.

### Phase 6: Installation & repo routes

- [ ] **6.1** Failing tests in `tests/test_routes_installations.py` (new) for the contracts in the RFC table: `POST /installations/intents` (owner) → 200 `{install_url}` = `https://github.com/apps/{settings.github_app_slug}/installations/new?state=<nonce>`, 500-guard when `github_app_slug` unset, 403 for members; `POST /installations/claim {installation_id, state}` (JWT-only) → 200 `{workspace_id}`, 400 on bad/expired state; `GET /installations` → linked list; `GET /installations/{installation_id}/available-repos` (owner) → annotated live list, 404 when unlinked; `DELETE /installations/{installation_id}` (owner) → 204 + repos soft-deleted; `POST /repos {installation_id, github_ids}` (owner) → 201 rows, 400 on ungranted id; `DELETE /repos/{repo_id}` (owner) → 204, 404 foreign repo. Members get 403 on every owner route.
- [ ] **6.2** Implement `app/routes/installations.py` (intents/claim/list/available-repos/unlink) and extend `app/routes/repos.py` (`POST /repos`, `DELETE /repos/{repo_id}`), schemas in `app/schemas/installation.py`; register in `app/main.py`. `_validate_production_secrets` in `app/config.py` now requires `github_app_slug` in production (it's load-bearing for the install URL). Suite green. Commit.

### Phase 7: Cleanup migration (drop `tenant_id`)

- [ ] **7.1** Grep `server/` for `GitHubInstallation.tenant_id` / `installation.tenant_id` — must be zero production references (tests updated in Phases 4-6).
- [ ] **7.2** Alembic migration `github_installations_global`: defensively de-duplicate on `installation_id` (keep oldest row; repoint `repositories.installation_id` and `tenant_installations.github_installation_id`; delete the rest); drop `tenant_id`; add `uq_github_installations_installation_id` UNIQUE(installation_id). Remove the `tenant_id` field from the model. Simplify `bind_installation`'s upsert to `ON CONFLICT (installation_id) DO UPDATE`.
- [ ] **7.3** Migration test: seed two pre-migration installations across two tenants, upgrade, assert links + constraint + FK integrity. Suite green. Commit.

### Phase 8: API rename + auth header + team response

- [ ] **8.1** Failing tests in `tests/test_auth.py`: `X-Workspace-Id` honoured; `X-Tenant-Id` still honoured as fallback; both present → `X-Workspace-Id` wins.
- [ ] **8.2** Implement in `app/auth.py` (`_parse_tenant_header` reads both); add `X-Workspace-Id` to CORS `allow_headers` in `app/main.py`.
- [ ] **8.3** Failing tests in `tests/test_routes_me.py` / `tests/test_routes_team.py`: paths `GET /me/workspaces`, `POST /me/active-workspace` (old paths 404); `GET /team` response field `workspace` (not `tenant`) including `is_default_name` — true for `name == "My Workspace"`, true for legacy `slug is not None and name == slug`, false after rename.
- [ ] **8.4** Implement: rename paths in `app/routes/me.py`; `app/schemas/team.py` `TeamResponse.tenant` → `workspace`, add `is_default_name` computed in `app/routes/team.py`; sweep user-facing "tenant" strings in route/service error details and the invitation email copy to "workspace". Suite green. Commit.

### Phase 9: Internal recompute filter

- [ ] **9.1** Failing test: `GET /internal/metrics/recompute-targets` excludes repos with `removed_at` set.
- [ ] **9.2** Add the filter in `app/routes/internal.py`. Suite green. Commit.

### Phase 10: Frontend — rename sweep + workspace context

- [ ] **10.1** Rename `client/src/lib/tenantContext.tsx` → `workspaceContext.tsx`: `WorkspaceProvider`, `useActiveWorkspace`, `useApiFetch` sends `X-Workspace-Id`; storage key `distilled.activeWorkspaceId` with a one-time read of the legacy `distilled.activeTenantId` key (then removed); fetches `GET /me/workspaces`, posts `/me/active-workspace`. `client/src/types/team.ts`: `TenantSummary` → `WorkspaceSummary`, team response `workspace` + `is_default_name`. Sweep components/copy: `ProfileMenu` ("Switch workspace"), `TeamPage` ("Delete workspace" etc.), `InvitationBanner`, `AcceptInvitePage`, `App.tsx`. Update all affected tests (assert the new header and storage key; legacy-key migration test).
- [ ] **10.2** Client suite green. Commit.

### Phase 11: Frontend — create workspace

- [ ] **11.1** Failing tests: `CreateWorkspaceModal` posts `/workspaces`, switches active workspace on success, disables submit on empty name; `ProfileMenu` shows "Create workspace" beneath memberships.
- [ ] **11.2** Implement `client/src/components/CreateWorkspaceModal.tsx` + `ProfileMenu` entry; after creation the empty workspace lands on `OnboardingScreen`. Green. Commit.

### Phase 12: Frontend — onboarding intent + setup callback

- [ ] **12.1** Failing tests for `OnboardingScreen`: on mount (owner) requests `POST /installations/intents` and renders the returned `install_url`; poll uses `useApiFetch` (asserts `X-Workspace-Id`); member sees "Ask the workspace owner to connect GitHub" instead of the install button (intent request 403 handled).
- [ ] **12.2** Implement; drop the `VITE_GITHUB_APP_SLUG`-built URL (env var no longer read — remove from `client/.env.example`). Green. Commit.
- [ ] **12.3** Failing tests for `client/src/pages/GitHubSetupPage.tsx`: signed-out → Clerk `<SignIn>` with redirect back (mirror `AcceptInvitePage`); signed-in → `POST /installations/claim` from query params, switch to returned workspace, redirect `/` with toast; claim error → inline error + guidance ("return to Distilled and reconnect from your workspace").
- [ ] **12.4** Implement page + `/github/setup` dispatch in `App.tsx` (alongside the `/invitations/accept` special case). Green. Commit.

### Phase 13: Frontend — Settings → Repositories

- [ ] **13.1** Failing tests: `RepositoriesPage` lists workspace repos with remove (confirm dialog: history retained but hidden) and connected installations with unlink (confirm dialog); `AddReposModal` lists available repos per linked installation with tracked ones disabled, submits `POST /repos`; "Connect GitHub" triggers the intent flow (navigates to `install_url`).
- [ ] **13.2** Implement `client/src/components/repos/RepositoriesPage.tsx` + `AddReposModal.tsx`; surface next to Team (extend the `showTeam` toggle in `App.tsx`/`ProfileMenu` into a small settings-section switch). Owner-only, same gating as `TeamPage`.
- [ ] **13.3** `InviteMemberModal`: replace `name === slug` with `is_default_name` from the team response. Client suite green. Commit.

### Phase 14: Seeds, docs, verification, PR

- [ ] **14.1** Update `server/scripts/seed_demo.py` / `claim_seed_data.py`: a user owning two workspaces, one installation linked to both, one repo in both workspaces, one sticky-removed repo.
- [ ] **14.2** Docs per RFC §Documentation: `docs/architecture.md` ("Workspaces (tenants in the schema)"), new ADR (rename-without-schema-rename + global installations), `docs/getting-started.md`, three READMEs (terminology + GitHub App Setup URL & "Redirect on update" setup), `docs/runbooks/webhook-redelivery.md`, `CONTRIBUTING.md` if contributor-facing workflow changed.
- [ ] **14.3** Full verification: server suite, client suite, lint/typecheck, `alembic upgrade head` from a pre-branch DB snapshot, manual smoke of the intent flow against a dev GitHub App (also verifies Risk 1 — `state` on the re-configure path; record the finding in the RFC's Risks section).
- [ ] **14.4** Push `feat/workspaces`, open PR titled "Workspaces: rename, creation, and repository management" with a summary referencing this RFC. No promo lines.
