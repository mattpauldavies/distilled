# Multi-User Tenants & Account Sharing

## Summary

Allow more than one user to access the same Distilled tenant, and allow a single user to belong to more than one tenant. Today every Clerk user is provisioned their own private tenant with no path to share it — engineering leaders cannot bring their team into the product without handing over credentials. This PRD introduces an explicit owner role on each tenant, an invitation flow for adding teammates (over GitHub-only sign-in), a tenant switcher for users with access to multiple workspaces, and the ability to remove members, transfer ownership, or leave a tenant. It also folds in the small set of changes needed to make the solo → team transition feel intentional: renaming the tenant when you invite your first teammate, and leaving (or deleting) a solo tenant once your team's "official" tenant exists.

---

## Problem

PRD 016 established a 1:1 mapping between Clerk users and tenants: the `users.tenant_id` column is a non-nullable FK created at first login and never changes. This was the right shape for solo onboarding, but it has four concrete consequences that block real customer use:

- A CTO who signs up cannot give their VP Eng or EMs visibility into the same metrics. The only workaround is sharing a Clerk login.
- An EM who tried Distilled solo before their CTO did has no path to join the company tenant — their personal tenant is permanent.
- Distilled data is organisational by nature — repositories, deployments, incidents — but the access model is personal. The mismatch is visible to every prospect within minutes of trial.
- There is no concept of an account "owner" distinct from a member, so we cannot reason about who is allowed to perform destructive actions (disconnect a GitHub installation, remove a repo, change billing later).

Multi-user access is the most common piece of feedback in early conversations and is a precondition for any pilot beyond a single individual.

---

## Goals

1. Allow a tenant to have multiple users, each authenticating via their own GitHub identity through Clerk, all seeing the same data.
2. Designate one user per tenant as the **owner** (the "primary" account holder) with rights to manage membership and rename the tenant.
3. Let the owner invite teammates by email and revoke access at any time, while keeping GitHub as the only sign-in method.
4. Allow a user to belong to **multiple tenants** and switch between them.
5. Let any user leave a tenant they're a member of, and let an owner leave by transferring ownership first (or deleting the tenant if they are its sole user).
6. Make the solo → team transition feel deliberate: prompt the owner to rename the tenant when they invite their first teammate.
7. Preserve the existing solo onboarding flow from PRD 016 — a new user signing up still gets a private tenant and is its owner.

---

## Non-Goals

- Granular roles beyond owner / member (no admin, billing-only, viewer, etc.).
- Per-repository or per-metric permissions. All members see all data in the tenant.
- Sign-in methods other than GitHub via Clerk. No email/password, no Google, no magic links — including for invitations.
- SSO, SCIM, or directory-sync provisioning. Invitations are manual and email-based.
- Domain-based auto-join (e.g. "anyone with an `@acme.com` email joins the Acme tenant").
- Audit logging of membership changes. Useful later, not required for v1.
- Billing or seat-based pricing. Tenants are unlimited members for now.
- Tenant deletion as a general feature. The narrow case of "owner is the only user, wants to leave" is supported as a side effect of leave; broader tenant lifecycle management is deferred.

---

## Users

**Primary (owner):** The engineering leader who signed up first and "owns" the Distilled account for their company. They want to bring in their EMs and direct reports without re-onboarding the data.

**Secondary (member):** An EM, staff engineer, or peer leader invited by the owner. They authenticate with their own GitHub account via Clerk and land directly in the shared tenant — no setup, no GitHub App install, no empty state.

**Tertiary (returning solo user):** Someone who tried Distilled before their company adopted it, has a personal tenant, and is now invited to the company tenant. They need to be able to switch between both, and to leave the personal one if they choose.

**Journey (owner):** dashboard → "Settings → Team" → invite first teammate → prompted to rename tenant from "Anna's tenant" to "Acme Engineering" → invite sent. Later: remove a member, or transfer ownership before leaving the company.

**Journey (member):** receive invitation email → click link → sign in with GitHub via Clerk → land on the shared dashboard with full data visibility. Tenant switcher in the header shows both their personal tenant (if any) and the new shared one.

---

## Concepts

### Tenant Membership

A **tenant membership** is the relationship between a user and a tenant, carrying a role. A user can hold many memberships (one per tenant they belong to). A tenant has a set of members; exactly one membership per tenant has `role = 'owner'`. Owners and members have identical read access to all tenant data; the only behavioural difference is that owners can manage membership, rename the tenant, and transfer ownership.

### Active Tenant

When a user belongs to multiple tenants, every API request must be unambiguous about which tenant it operates in. The frontend tracks an **active tenant** (persisted per-user in the database) and sends it on each request. The backend rejects any request whose active tenant the user is not a member of.

### Invitations

An invitation is a pending grant of membership against an email address or GitHub username. It exists as a row in the database before any user record does — the invited person may not have a Clerk account yet. When they sign in for the first time, the invitation is consumed and a new membership is created in the inviting tenant. Existing users who accept an invitation simply gain an additional membership; they don't lose their existing tenant access.

### Ownership Transfer

A tenant always has exactly one owner. Transfer is a single atomic action: the current owner picks an existing member and promotes them; the old owner becomes a regular member. This avoids a "no owner" state and avoids needing co-owners.

---

## Data Model Changes

### Modified: `users` table

`tenant_id` is removed from `users` — it doesn't make sense once a user can belong to multiple tenants. Existing rows are migrated to a single membership row each (see Migration below).

| Column | Change | Notes |
|---|---|---|
| `tenant_id` | **removed** | replaced by `tenant_memberships` |
| `active_tenant_id` | **new**, UUID FK → tenants, nullable | the user's currently selected tenant; nullable only transiently between sign-up and first membership creation |

### New: `tenant_memberships` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → users NOT NULL | |
| `tenant_id` | UUID FK → tenants NOT NULL | |
| `role` | TEXT NOT NULL | enum: `'owner' \| 'member'` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

Constraints:
- `UNIQUE (user_id, tenant_id)` — a user has at most one membership per tenant.
- `CREATE UNIQUE INDEX ON tenant_memberships (tenant_id) WHERE role = 'owner'` — at most one owner per tenant.

### New: `invitations` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants NOT NULL | tenant being shared |
| `email` | TEXT | normalised lowercase; nullable when invited by GitHub username |
| `github_username` | TEXT | nullable; set when invited by handle instead of email |
| `invited_by_user_id` | UUID FK → users NOT NULL | for display in the UI |
| `token` | TEXT UNIQUE NOT NULL | unguessable secret embedded in invite link |
| `status` | TEXT NOT NULL | `'pending' \| 'accepted' \| 'revoked' \| 'expired'`, default `'pending'` |
| `expires_at` | TIMESTAMPTZ NOT NULL | default `created_at + 14 days` |
| `accepted_at` | TIMESTAMPTZ | set when redeemed |
| `accepted_by_user_id` | UUID FK → users | set when redeemed |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

Constraints:
- `CHECK (email IS NOT NULL OR github_username IS NOT NULL)` — at least one addressing field set.
- Partial unique on `(tenant_id, lower(email)) WHERE status = 'pending' AND email IS NOT NULL`.
- Partial unique on `(tenant_id, lower(github_username)) WHERE status = 'pending' AND github_username IS NOT NULL`.

### Modified: `tenants` table

Add `name` (TEXT NOT NULL) — the human-friendly display name shown in the tenant switcher and team page. The existing `slug` is retained but is no longer the primary display string.

### Migration

A single migration:
1. Adds `tenants.name` (default: derived from `slug` for existing rows).
2. Adds `tenant_memberships` and `invitations`.
3. For every existing `users` row, inserts a `tenant_memberships` row with `role = 'owner'` and copies `users.tenant_id` to `tenant_memberships.tenant_id`.
4. Sets `users.active_tenant_id = users.tenant_id`.
5. Drops `users.tenant_id`.

---

## GitHub-Only Sign-In × Invitations

Sign-in remains GitHub-only via Clerk. The friction this creates with email-based invitations is the email mismatch case: the owner invites `sam@acme.com`, but Sam's primary GitHub email is `sam@personal.com`. Two design decisions resolve this:

1. **Match against all verified Clerk emails.** Clerk surfaces every verified email address attached to a user's GitHub account, not just the primary. Invitation redemption checks the pending invitation's email against the full set of the user's verified emails. If any one matches, the invitation is redeemed.
2. **Allow a fallback by GitHub username.** The invite modal accepts either an email **or** a GitHub username (autodetected by the presence of `@`). When invited by username, redemption matches against the new user's `github_username` / `github_account_id` from Clerk's GitHub OAuth claims rather than email. This is the recommended path inside engineering orgs where teammates know each other's handles, and avoids the verified-email problem entirely.

Both matching strategies are tried at redemption time. The owner doesn't need to know which one will work — they pick whichever identifier they have for the teammate.

---

## Backend Changes

### Tenant Resolution (PRD 016 → updated)

The auto-provisioning logic in `middleware/tenant.py` becomes:

1. Look up `User` by `clerk_user_id`.
   - If found: read `active_tenant_id`, verify the corresponding membership still exists, return it. (See "Active Tenant Switching" for the request-time override.)
2. If not found, look for any **pending invitations** matching either:
   - any verified Clerk email address on the new identity, or
   - the GitHub username / account ID from the GitHub OAuth claim.
   For each match: create a `tenant_memberships` row with `role = 'member'`, mark the invitation `accepted`. Set `active_tenant_id` to the most recently created of these.
3. If at least one invitation was redeemed in step 2, return the new active tenant.
4. Otherwise: existing behaviour — create a new `Tenant`, create a `users` row, and create a single `tenant_memberships` row with `role = 'owner'`. Set `active_tenant_id` to the new tenant.

This keeps the solo onboarding path identical and treats invitation redemption as a side effect of normal sign-in. Multiple invitations to the same person can all be redeemed in one sign-in.

### Active Tenant Switching

A new endpoint `POST /api/me/active-tenant` accepts `{tenant_id}`. The backend verifies the user has a membership in that tenant, updates `users.active_tenant_id`, and returns 204. All subsequent API requests resolve to that tenant via the existing tenant middleware (which now reads `active_tenant_id` instead of the removed `users.tenant_id` FK).

For request-time override (e.g. opening Distilled in two tabs against two tenants), an optional `X-Tenant-Id` header takes precedence over `active_tenant_id` if the user is a member of the requested tenant. Otherwise return 403.

### New Endpoints

All endpoints below require Clerk JWT auth (PRD 016) and operate within the caller's active tenant unless noted.

| Method | Path | Caller role | Purpose |
|---|---|---|---|
| `GET` | `/api/me/tenants` | any auth | list tenants the current user is a member of, with role |
| `POST` | `/api/me/active-tenant` | any auth | switch active tenant |
| `GET` | `/api/team/members` | any member | list users in the active tenant (id, email, github_username, role, created_at) |
| `GET` | `/api/team/invitations` | any member | list pending invitations |
| `POST` | `/api/team/invitations` | owner | create an invitation `{email_or_username}` → sends email, returns invitation row |
| `DELETE` | `/api/team/invitations/{id}` | owner | revoke a pending invitation |
| `POST` | `/api/team/invitations/{id}/resend` | owner | re-send the invitation email (no token rotation) |
| `DELETE` | `/api/team/members/{user_id}` | owner | remove a member from the tenant |
| `POST` | `/api/team/transfer-ownership` | owner | `{new_owner_user_id}` — atomically swap the owner role |
| `POST` | `/api/team/leave` | any member | leave the active tenant; owners must transfer first unless they are the sole user |
| `PATCH` | `/api/tenant` | owner | update the tenant `{name}` |

Authorization is enforced by `require_owner` and `require_member` dependencies that read the caller's role from `tenant_memberships` for the active tenant.

### Removing a Member

Deleting the `tenant_memberships` row is sufficient — the user retains their Clerk identity and any other tenant memberships they hold. If the removed user's `active_tenant_id` pointed at the tenant they were just removed from, set it to the most recently created of their remaining memberships, or `null` if they have none. Their next sign-in falls through to step 4 of tenant resolution if they have no remaining memberships, identical to today's solo-provisioning behaviour.

### Leaving a Tenant

`POST /api/team/leave` rules:
- **Member:** delete the membership; reset `active_tenant_id` if needed; return 204.
- **Owner with other members:** return 400 with a clear message ("Transfer ownership first").
- **Owner with no other members:** delete the tenant and all its data in a transaction. This is the only tenant-deletion path in v1 and is intentionally reachable only from this narrow case to avoid scope creep on lifecycle management. The user is reset to their next-most-recent tenant membership or, if none, the next sign-in re-provisions a solo tenant per PRD 016.

### Transferring Ownership

Single transaction, demote-then-promote to respect the partial unique constraint:
```sql
UPDATE tenant_memberships SET role = 'member' WHERE id = :current_owner_membership_id;
UPDATE tenant_memberships SET role = 'owner'  WHERE user_id = :new_owner_user_id AND tenant_id = :tenant_id;
```

### Tenant Rename

`PATCH /api/tenant` taking `{name}`. Validation: 1–60 characters, trimmed. The owner is prompted to rename when they create their first invitation (see Frontend), but they can rename any time afterwards from the team page.

### Email Delivery (decoupled from Clerk)

Invitation emails are sent through a dedicated transactional provider — **Resend** is the recommended choice (developer-first, simple SDK, low ops cost). This decouples our membership model from Clerk's invitation primitive, which we'll need to detangle eventually for billing receipts, future digest emails, and broader product comms.

Configuration:
- `RESEND_API_KEY` (Railway env var)
- `EMAIL_FROM_ADDRESS` (e.g. `noreply@distilled.<tld>`)
- `EMAIL_FROM_NAME` (e.g. `Distilled`)

Email content:
- Subject: `<Owner name> invited you to <Tenant name> on Distilled`
- Body: short, on-brand, dark-themed HTML with a single CTA linking to `https://<app>/invite?token=<token>`.
- The link routes to a Clerk GitHub sign-in page; the token is exchanged server-side after authentication completes.

Username-based invitations do not produce an outbound email (there's no address to send to). Instead, the invitation appears in the team page's pending list and the owner is responsible for nudging the teammate via their own channel (Slack, etc.). The email/username distinction is shown in the pending list.

### Local Dev Seed Data

The existing seed script is updated to provision multi-tenant fixtures so we can exercise switching, invitations, and ownership flows locally without external email:

- Two tenants: `Acme Engineering` and `Anna's Personal`.
- Three users: Anna (owner of Acme, owner of Anna's Personal), Ravi (member of Acme), Sam (member of Acme, with a previously redeemed invitation in their history).
- One outstanding pending invitation against `jules@acme.com`.

Seed data is keyed by stable Clerk dev-account IDs documented in the dev setup guide.

---

## Frontend Changes

### Tenant Switcher

A new compact dropdown in the top-left of the global header showing the active tenant name. Clicking it lists all tenants the user is a member of, each with a role badge. Selecting a tenant calls `POST /api/me/active-tenant` and reloads the dashboard.

For single-tenant users, the switcher renders as a static label (no chevron) so the chrome cost is zero.

### Settings → Team Page

A new screen under the existing settings area, accessible to all members but with management controls visible only to the owner.

```
┌──────────────────────────────────────────────────────────┐
│  Acme Engineering                          [Rename]      │
│                                                          │
│  Members (3)                            [Invite member]  │
│  ──────────────────────────────────────────────────────  │
│  Anna Chen           anna@acme.com       Owner           │
│  Ravi Patel          ravi@acme.com       Member    [⋯]   │
│  Jules Okafor        jules@acme.com      Member    [⋯]   │
│                                                          │
│  Pending invitations (1)                                 │
│  ──────────────────────────────────────────────────────  │
│  sam@acme.com        Sent 2 days ago     [Resend][✕]    │
│                                                          │
│  ──────────────────────────────────────────────────────  │
│  [Leave tenant]                                          │
└──────────────────────────────────────────────────────────┘
```

- The `[⋯]` menu (owner-only) offers **Remove** and **Transfer ownership**. Both require a confirmation dialog naming the affected member.
- For non-owners, the page is read-only (no rename, no `[⋯]`, no invite button) but the **Leave tenant** action is always available to non-owners.
- For the owner, **Leave tenant** is disabled with a tooltip ("Transfer ownership first") if there are other members; enabled with a stronger confirmation ("This will permanently delete the tenant and all its data") if they are the sole user.

### Solo → Team Rename Prompt

When the owner clicks **Invite member** for the first time on a tenant whose name is still the auto-generated default (e.g. `Anna's tenant`), a one-time modal appears **before** the invite modal:

```
┌──────────────────────────────────────────────┐
│  Name your team                              │
│                                              │
│  You're about to invite a teammate. Give     │
│  your tenant a name they'll recognise.       │
│                                              │
│  Team name: [ Acme Engineering        ]      │
│                                              │
│           [Skip for now]    [Continue →]     │
└──────────────────────────────────────────────┘
```

"Continue" calls `PATCH /api/tenant` then opens the invite modal. "Skip for now" opens the invite modal directly without renaming, and the prompt does not appear again on subsequent invites (one-time only). Owners can always rename later via the **Rename** button on the team page.

### Invite Modal

Single field accepting either an email address or a GitHub username (autodetected by the presence of `@`). Inline validation. Submits to `POST /api/team/invitations`. Errors (duplicate pending invite, already a member, malformed input) render below the field.

### Sign-In via Invitation

No new page needed. The invited email link routes the user through Clerk's existing GitHub sign-in. The first authenticated API call invokes the updated tenant resolver, which redeems the invitation transparently and sets the active tenant. The user lands on the shared dashboard.

A small one-time toast — `Welcome to <Tenant name>` — appears on first load after redemption to confirm they're in the right place.

### Header / Account Menu

The existing user menu gains a single line: a "Member" or "Owner" badge for the active tenant. The tenant name itself lives in the tenant switcher rather than the account menu.

---

## Documentation

The following docs must land alongside the implementation:

- **Getting Started guide** (`docs/getting-started.md`, new): a short walkthrough covering sign-in, the solo → team transition (including the rename prompt), inviting teammates by email or GitHub username, switching between tenants, and the path for "I tried Distilled solo and just got invited to my company's tenant" — including how to leave or delete a personal tenant.
- **`/docs/architecture.md`**: update the auth and tenant-resolution sections to describe the new join-table model and active-tenant header.
- **`/server/README.md`**: document the new env vars (`RESEND_API_KEY`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`) and the seed data shape.
- **ADR**: a short ADR documenting "Tenant membership as a join table; one user → many tenants" so future contributors don't trip on the PRD-016 1:1 assumption.

---

## Edge Cases & Behaviour

- **Invitee already has a Distilled tenant of their own.** Allowed — they gain a second membership and can switch between tenants. The newly accepted tenant becomes their active tenant on first sign-in after redemption.
- **Owner tries to remove themselves via `DELETE /members`.** Blocked by API. Use **Leave tenant** instead, which enforces the transfer-or-sole-user rule.
- **Owner tries to transfer to a non-member.** Blocked. Transfer target must already be a member of the tenant.
- **Owner is the sole user and leaves.** The tenant and all its data are deleted in a transaction. The user is reset to their next-most-recent membership or, if none, signs in afresh and gets a new solo tenant per PRD 016.
- **Invitation expires.** `status` flips to `'expired'` via a periodic job (or lazily on read). The owner can re-issue from the team page.
- **Invitation revoked after sign-in but before first API call.** Race is acceptable: the redeem-on-resolve step reads `status = 'pending'` under a row lock; if it's been revoked, that invitation is skipped and the user falls through to step 4 if no other invitations apply. No data leaks.
- **Email mismatch with no verified work email.** If the invitee's GitHub account does not have the invited address as a verified email and the invitation wasn't created against their GitHub username, the invitation will not auto-redeem. The invitation page shows a clear message explaining the mismatch and suggesting the owner re-invite by GitHub username.
- **GitHub App installation context.** The installation remains tenant-scoped. Members do not need to re-install or re-authorise the GitHub App — they inherit access through tenant membership.
- **Two tabs, two tenants.** Setting `X-Tenant-Id` per request lets a power user keep one tab on each tenant without `active_tenant_id` thrash. The frontend sets this header from the tenant context of the currently rendered route.

---

## Acceptance Criteria

### Membership
- [ ] A tenant created via solo sign-up has exactly one membership, role `owner`.
- [ ] A tenant can have at least 10 members in addition to the owner without performance regression on dashboard load.
- [ ] All members see identical data via the dashboard and API.
- [ ] At most one membership per tenant has `role = 'owner'` at any time (DB constraint enforced).
- [ ] A user can hold memberships in multiple tenants simultaneously.

### Invitations
- [ ] An owner can invite a teammate by email; the teammate receives an email via Resend within 30 seconds.
- [ ] An owner can invite by GitHub username; no email is sent, and the invitation redeems on the next sign-in by the matching GitHub account regardless of the user's email.
- [ ] An invited user whose verified Clerk emails include the invited address redeems successfully even if the invited address is not their GitHub primary.
- [ ] A non-owner cannot create, revoke, or resend invitations (API returns 403; UI hides controls).
- [ ] A pending invitation cannot be created twice for the same email + tenant or username + tenant.
- [ ] Invitations expire after 14 days and cannot be redeemed thereafter.
- [ ] An owner can revoke a pending invitation; subsequent attempts to redeem the link fail.

### Tenant Switching
- [ ] A user with two memberships sees both in the tenant switcher.
- [ ] Selecting a tenant in the switcher updates `active_tenant_id` and reloads the dashboard against that tenant's data.
- [ ] Two browser tabs scoped to two different tenants via `X-Tenant-Id` do not interfere with each other.
- [ ] A user attempting to access a tenant they're not a member of (via direct API call) receives 403.

### Removal & Leaving
- [ ] An owner can remove a member; that member loses access on their next API call, while retaining any other memberships.
- [ ] A member can leave a tenant on their own; their membership is deleted and `active_tenant_id` resets cleanly.
- [ ] An owner with other members cannot leave; the API returns 400 and the UI directs them to transfer first.
- [ ] An owner who is the sole user of a tenant can leave; the tenant and all its data are deleted.

### Ownership Transfer
- [ ] An owner can transfer ownership to any existing member in a single action.
- [ ] After transfer, the new owner has management rights and the old owner sees only read-only team controls.
- [ ] Ownership transfer to a non-member or non-existent user fails with 400.
- [ ] At no point during transfer does the tenant have zero or two owners.

### Solo → Team Transition
- [ ] On the first invite from a tenant whose name is still the auto-generated default, the rename prompt appears.
- [ ] Skipping the rename prompt does not block the invite, and the prompt does not appear again on subsequent invites.
- [ ] An owner can rename the tenant from the team page at any time.

### Local Development
- [ ] Seed data provisions at least two tenants, three users with mixed memberships, and one pending invitation, sufficient to manually exercise switching, leaving, and transfer flows.

---

## Open Questions

1. **Member visibility of pending invitations.** The PRD currently shows the pending invitations list to all members (so they can see who's coming), but only owners can act on them. An alternative is owner-only visibility, which slightly reduces the social signal of "who is being courted to join". Confirm the team-page-for-everyone read model is what we want.

2. **Default active tenant on sign-in for a returning user with multiple tenants.** Their last-used (`active_tenant_id`) is the obvious default. But a freshly redeemed invitation arguably should win for that one session ("we just brought you here, here you are"). The PRD currently picks the latter — confirm this is the desired behaviour.

3. **Tenant deletion scope.** v1 only allows tenant deletion as a side-effect of a sole-owner leaving. Should we also expose an explicit "Delete tenant" action on the team page for that same case (sole owner), to make the destructive action more visible than hiding it behind "Leave"? Mild UX improvement, no extra backend work.
