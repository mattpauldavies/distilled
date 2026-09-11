# ADR 009: Workspaces rename without schema rename; installations as global resources

## Status

Accepted (RFC 026)

## Context

The product renamed tenants to **workspaces** and made them multiple-per-user:
users create workspaces, connect GitHub App installations to them, and curate
per-workspace repository sets. Two design decisions from RFC 026 need a durable
record because the code will otherwise look inconsistent to future contributors.

## Decision 1: product-surface rename only

"Workspace" is the product term everywhere a user or API consumer sees it: UI
copy, API routes (`/workspaces`, `/me/workspaces`, `/me/active-workspace`), the
`X-Workspace-Id` header, JSON field names, and docs. The **database schema and
existing server-side identifiers keep their `tenant` names** (`tenants`,
`tenant_users`, `tenant_id`, `require_auth`'s tenant resolution, etc.), and new
DB objects follow the existing convention (`tenant_installations`).

Rationale: a full rename is ~2,500 mechanical touches plus a table-rename
migration with zero behaviour change — high regression risk for cosmetic
benefit. The seam is documented here and in `docs/architecture.md`: **workspace
(product) ≡ tenant (schema)**. `X-Tenant-Id` remains accepted as a header
fallback. A follow-up internal rename can be its own RFC if the seam proves
costly.

## Decision 2: installations are global, linked to workspaces

A GitHub App installs at most once per GitHub account, so two users tracking
repos from the same organisation necessarily share one installation.
`github_installations` therefore holds one global row per installation
(unique on `installation_id`, no `tenant_id`), and `tenant_installations`
links workspaces to installations many-to-many.

Binding is explicit, never inferred: connecting GitHub mints an **installation
intent** (workspace + user + hashed nonce), carried through GitHub's `state`
parameter and claimed by the setup callback, with webhook **sender matching**
as a fallback. The previous heuristic — matching `installation.account.id`
against a user and picking an owned tenant with `LIMIT 1` — was deleted: it
silently dropped organisation installs (an org's account id never matches a
user) and became nondeterministic once a user owned two workspaces.

Repositories stay per-workspace rows (`UNIQUE(tenant_id, github_id)`); webhook
ingest fans out one event into every workspace tracking the repo. Webhook
syncs respect **sticky removals** (a repo an owner removed stays removed);
only explicit user actions resurrect.

## Consequences

- The same GitHub repo in N workspaces stores and recomputes its data N times.
  Acceptable at current scale; the fan-out loops in `ingest_pr_service` and
  `ingest_deployment_service` are the seam to revisit if that changes.
- An installation created without an intent (e.g. installed directly from
  GitHub) is held unclaimed — recorded globally, attached to no workspace —
  until a user runs the connect flow.
- Grep habits: product-facing code says workspace, persistence says tenant.
