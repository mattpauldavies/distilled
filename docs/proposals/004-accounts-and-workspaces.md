# Accounts, Workspaces and Access

**Status:** Shipped
**Consolidates:** PRD 016 (SaaS tenant creation), PRD 017 (multi-user tenants), RFC 016, RFC 021, RFC 026 (workspaces), ADR 001 (Clerk), ADR 002 (multi-user tenancy), ADR 009 (workspaces rename), ADR 010 (installation claim authorisation)

## Summary

How a stranger becomes a user, how a user gets data, and how several users share it. The
product term is **workspace**; the database schema says `tenant`. They are the same thing —
see the rename decision below.

This is the one area of Distilled that changed shape three times, so the design is recorded
as it stands today, with the evolution in the History section rather than spread across
three superseding documents.

## The journey

1. Sign in with GitHub via Clerk.
2. A workspace named "My Workspace" is provisioned automatically, with the signed-in user as
   its owner.
3. The empty workspace shows an onboarding screen; the user connects the GitHub App and
   picks repositories.
4. Optionally: rename the workspace, invite teammates, create further workspaces, switch
   between them.

## Identity

**Clerk** is the identity provider, with GitHub as the only sign-in method. Application code
handles no OAuth secrets, no passwords, and no sessions.

The backend verifies Clerk's RS256 JWTs against a JWKS endpoint cached in-process for an
hour. No Clerk SDK is used server-side — just `PyJWT` — and audience and issuer are both
verified. The frontend uses `@clerk/clerk-react` for the sign-in widget and
`useAuth().getToken()` to attach the session token to every request.

Stateless verification is what makes this work across multiple Railway instances: no sticky
sessions, no Redis, no shared session store. The JWKS cache is per-worker, which is safe
because Clerk's keys are identical across processes and rotate rarely.

Provisioning happens on the first authenticated request from an unseen Clerk user ID, in one
transaction, guarded against the concurrent-first-login race by an `IntegrityError` retry.
There is no separate registration step.

## Workspaces and membership

Membership is a `tenant_users` row: `(user_id, tenant_id, role)` where role is `owner` or
`member`. A partial unique index `WHERE role = 'owner'` enforces exactly one owner per
workspace **at the database level**, so there is no "no owner" or "two owners" state at any
point during an ownership transfer.

Owners and members have identical read access to all workspace data. The difference is
purely destructive capability: only owners manage membership, rename or delete the
workspace, and add, remove, or unlink repositories and installations.

A user can own or belong to any number of workspaces. `POST /workspaces` creates one;
first-login provisioning uses the same code path.

### Active workspace

The active workspace is **per request**, not per user:

1. `X-Workspace-Id` header, membership verified server-side (`X-Tenant-Id` still accepted as
   a fallback).
2. Otherwise `users.last_active_tenant_id`, lazily updated when it changes.
3. Otherwise 409, and the client routes to onboarding.

A header naming a workspace the user does not belong to returns 403; the client clears the
stale value and falls back.

Making this request-scoped is what lets one Clerk session drive two tabs on two different
workspaces without either clobbering the other.

### Invitations

An invitation is a pending grant of membership against an email address. The link is the
credential: a 32-byte URL-safe token, of which only the SHA-256 hash is stored. The raw
token leaves the server exactly once, in the email body.

Redemption is bundled into the first sign-in — click the link, sign in with **any** GitHub
account, and the page fires `POST /invitations/redeem` automatically. There is no preview
step; the user has already read the inviter and workspace name in the email.

The invitee's GitHub email does not need to match the address invited. That is the whole
point: it keeps GitHub-only sign-in viable without forcing people to add a specific email to
their GitHub account. Email is the delivery channel, not the authorisation.

For someone who signs in normally without clicking their link, the backend matches their
verified GitHub emails against pending invitations and surfaces a banner with explicit
Accept and Decline. That is the only place email is used for anything beyond delivery, and
it is opt-in.

Invitations expire after 14 days, enforced inline at redeem time; a scheduled job is a
janitor, not the correctness mechanism.

Email delivery sits behind an `EmailService` protocol with `ResendEmailService` for
production and `LoggingEmailService` for dev and tests — the accept URL is printed to the
server log, so invitations can be tested end to end without an inbox.

A rejected send raises `EmailDeliveryError` carrying Resend's own `name` and `message` from
the response body, logged at ERROR before it is raised. The caller still sees a 500, but the
log line and the Sentry title name the cause — unverified sending domain, restricted key,
sandbox-only recipient — instead of a bare status code.

### Leaving, transferring, deleting

- Members can leave at any time; other memberships are unaffected.
- Owners have no Leave option. To step back they transfer ownership first, in a single
  action that demotes the current owner and promotes a member.
- An owner who is the **sole** user can delete the workspace. This is a separate, clearly
  destructive action, not conflated with leaving.

Deletion is one `DELETE FROM tenants WHERE id = ...`: every workspace-scoped foreign key
carries `ON DELETE CASCADE`.

## GitHub installations

A GitHub App installs **at most once per GitHub account**. Two users who both want
`acme/api` in their own private workspaces cannot create two installations on `acme` — they
necessarily share one. Everything below follows from that constraint.

`github_installations` is therefore a **global** table: one row per installation, unique on
`installation_id`, owned by no workspace. `tenant_installations` links workspaces to
installations many-to-many.

### Binding is explicit, never inferred

Connecting GitHub to a workspace mints an **installation intent** — workspace, user, hashed
nonce, 30-minute TTL — and the nonce travels through GitHub's `state` parameter. The setup
callback claims it.

Because the callback receives a client-supplied `installation_id`, and installation IDs are
small sequential integers, a claim must prove the caller controls the installation. Without
that proof, any signed-up user could bind an arbitrary organisation's installation to their
own workspace and start receiving that organisation's private repository list and webhook
data. The proof depends on account type:

- **User installations** — the installation's `account.id`, fetched from GitHub with the app
  JWT, must equal the caller's `github_account_id`. Binds immediately.
- **Organisation installations** — the app-JWT fetch does not identify who installed it, and
  we deliberately avoid requiring org-members-read permission or Clerk-brokered user OAuth
  tokens. The only GitHub-authenticated evidence of control we hold is the installation
  webhook's `sender`, so org installs bind **exclusively** via sender matching. The callback
  answers `202 pending` without consuming the intent and the client polls until the webhook
  lands.

An installation already bound to the intent's workspace claims without re-proving —
reconnecting something the workspace already has grants nothing new.

The predecessor to this was a heuristic: match `installation.account.id` against a user,
then pick one of their owned workspaces with `LIMIT 1` and no ordering. It silently dropped
every organisation install (an org's account ID never matches a user row) and became
non-deterministic as soon as a user owned two workspaces. It was deleted.

### Repositories

Repositories are per-workspace rows, `UNIQUE(tenant_id, github_id)`. The same GitHub repo
tracked by three workspaces is three rows, each accumulating its own PRs, deployments,
environments, and metrics; webhook ingest fans one event out to all of them.

- **Add** — owners pick from the installation's live grant list, fetched from GitHub at
  request time. There is no local repo catalogue, so there is no staleness surface and no
  reconciliation job.
- **Remove** — soft delete in that workspace only, retaining history.
- **Removals are sticky** — webhook syncs never resurrect a repo an owner removed. Only
  explicit user actions do.
- **Move between workspaces** — remove in one, add in the other. History stays with the
  soft-deleted row; there is no dedicated move action.

## Decisions

**Clerk over rolling our own OAuth, Auth0, or NextAuth.** Rolling our own means managing
OAuth secrets, callbacks, session storage, and CSRF — high complexity, high risk, no
differentiation. Auth0 has more complex pricing and a less pleasant React SDK. NextAuth does
not apply to a FastAPI backend.

**Our own tenancy tables, not Clerk Organizations.** Clerk's organisations primitive could
model membership, but it would couple tenant identity to Clerk and bind invitation
lifecycles to Clerk's email pipeline. Tenant data stays sovereign in our database; Clerk
owns identity only.

**Resend rather than Clerk's invitation primitive.** Clerk's invites are tightly coupled to
its own user model and do not extend to future product mail — digests, billing receipts. A
provider-agnostic protocol keeps identity and messaging separate.

**Email failures carry the provider's message.** `raise_for_status()` throws the response
body away, so a production 403 from Resend reached Sentry with nothing to distinguish an
unverified domain from a restricted key from a sandbox-only recipient. `ResendEmailService`
now reads the body's `message` (and `name`) itself, mirroring `_github_message` in
`github_client`. The detail is truncated to 500 characters so an HTML error page from an
edge proxy can't flood the log.

**`tenant_users`, not `tenant_memberships`.** Matches the codebase's plural-noun table style
and reads as "the join between tenants and users" rather than introducing an abstract noun.

**Rename the product surface only.** "Workspace" is the term in UI copy, API routes, the
`X-Workspace-Id` header, JSON fields, and docs. The database schema and existing server-side
identifiers keep their `tenant` names, and new DB objects follow the existing convention
(`tenant_installations`). A full rename is roughly 2,500 mechanical touches plus a
table-rename migration with zero behaviour change — high regression risk for cosmetic
benefit. The seam costs one thing: grep habits. Product-facing code says workspace,
persistence says tenant. A follow-up internal rename can be its own proposal if that proves
costly.

**Default workspace name is "My Workspace", with `slug` deprecated.** Naming the first
workspace after the GitHub username gave the second workspace a globally-unique-slug
collision. New workspaces get `slug = NULL`; the column is kept for existing rows and read
only by legacy default-name detection, which the server now computes and exposes as
`is_default_name`.

**One extra query per authenticated request.** Membership resolution adds an indexed join,
replacing the previous direct lookup, so the per-request cost is similar.

## Accepted consequences

- The same GitHub repo in N workspaces stores and recomputes its data N times. Acceptable at
  current scale; the fan-out loops in `ingest_pr_service` and `ingest_deployment_service` are
  the seam to revisit.
- An installation created directly from GitHub, with no intent, is recorded globally and
  attached to nothing until a user runs the connect flow.
- A configure-only visit to an existing org installation that changes nothing fires no
  webhook, so it cannot complete a **new** workspace binding by itself. The pending state
  tells the user that adjusting the repository selection will complete the connection.
- Two codepaths join a workspace: token redemption and banner acceptance.

## Out of scope

Roles beyond owner and member; per-repository or per-metric permissions; sign-in methods
other than GitHub; SSO, SCIM, or domain-based auto-join; audit logging of membership
changes; billing and seat limits; workspace quotas; transferring installations between
workspaces; handling `installation.suspend`.

## History

- **PRD 016 / RFC 016 / ADR 001** replaced the static API key with Clerk JWTs, added
  auto-provisioning, and built the onboarding screen. One user, one tenant, permanently.
- **PRD 017 / RFC 021 / ADR 002** replaced that 1:1 mapping with `tenant_users`, added
  invitations, the `X-Tenant-Id` header, roles, and tenant switching.
- **RFC 026 / ADR 009** renamed tenants to workspaces on the product surface, made
  workspaces creatable, globalised installations behind `tenant_installations`, and
  introduced installation intents.
- **ADR 010** (security review, September 2026) added proof-of-control to installation
  claims, closing a critical cross-workspace data-exposure hole in the intent flow.
