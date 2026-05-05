# Multi-User Tenants & Account Sharing

## Summary

Allow more than one user to access the same Distilled tenant. Today every Clerk user is provisioned their own private tenant with no path to share it — engineering leaders cannot bring their team into the product without handing over credentials. This PRD introduces an explicit owner role on each tenant, an invitation flow for adding teammates, and the ability to remove members or transfer ownership. Tenants remain a single, shared workspace; this PRD does not introduce per-resource permissions or multiple workspaces per user.

---

## Problem

PRD 016 established a 1:1 mapping between Clerk users and tenants: the `users.tenant_id` column is a non-nullable FK created at first login and never changes. This was the right shape for solo onboarding, but it has three concrete consequences that block real customer use:

- A CTO who signs up cannot give their VP Eng or EMs visibility into the same metrics. The only workaround is sharing a Clerk login.
- Distilled data is organisational by nature — repositories, deployments, incidents — but the access model is personal. The mismatch is visible to every prospect within minutes of trial.
- There is no concept of an account "owner" distinct from a member, so we cannot reason about who is allowed to perform destructive actions (disconnect a GitHub installation, remove a repo, change billing later).

Multi-user access is the most common piece of feedback in early conversations and is a precondition for any pilot beyond a single individual.

---

## Goals

1. Allow a tenant to have multiple users, each authenticating via their own Clerk identity, all seeing the same data.
2. Designate one user per tenant as the **owner** (the "primary" account holder) with rights to manage membership.
3. Let the owner invite teammates by email and revoke access at any time.
4. Let the owner transfer ownership to another member without losing data continuity.
5. Preserve the existing solo onboarding flow from PRD 016 — a new user signing up still gets a private tenant, and they are the owner of it.

---

## Non-Goals

- Granular roles beyond owner / member (no admin, billing-only, viewer, etc.).
- Per-repository or per-metric permissions. All members see all data in the tenant.
- Multiple tenants per user. A user belongs to exactly one tenant at a time. Switching tenants is out of scope.
- SSO, SCIM, or directory-sync provisioning. Invitations are manual and email-based.
- Domain-based auto-join (e.g. "anyone with an `@acme.com` email joins the Acme tenant").
- Audit logging of membership changes. Useful later, not required for v1.
- Billing or seat-based pricing. Tenants are unlimited members for now.

---

## Users

**Primary (owner):** The engineering leader who signed up first and "owns" the Distilled account for their company. They want to bring in their EMs and direct reports without re-onboarding the data.

**Secondary (member):** An EM, staff engineer, or peer leader invited by the owner. They authenticate with their own GitHub account via Clerk and land directly in the shared tenant — no setup, no GitHub App install, no empty state.

**Journey (owner):** dashboard → "Settings → Team" → enter teammate email → send invite. Later: remove a member, or transfer ownership before leaving the company.

**Journey (member):** receive invitation email → click link → sign in with GitHub via Clerk → land on the shared dashboard with full data visibility.

---

## Concepts

### Tenant Membership

A tenant has a set of users. One of those users is the **owner**. Every other user is a **member**. Members and owners have identical read access to all tenant data; the only behavioural difference is that owners can manage membership and transfer ownership.

### Invitations

An invitation is a pending grant of membership against an email address. It exists as a row in the database before any user record does — the invited person may not have a Clerk account yet. When they sign in for the first time, the invitation is consumed: instead of provisioning a new private tenant for them (the PRD 016 default), they are attached to the inviting tenant as a member.

### Ownership Transfer

A tenant always has exactly one owner. Transfer is a single atomic action: the current owner picks an existing member and promotes them; the old owner becomes a regular member. This avoids a "no owner" state and avoids needing co-owners.

---

## Data Model Changes

### Modified: `users` table

The current schema has `tenant_id` as a non-nullable FK with no role information. Two changes:

| Column | Change | Notes |
|---|---|---|
| `tenant_id` | unchanged | still FK → tenants, still non-null, still exactly one tenant per user |
| `role` | **new**, TEXT NOT NULL | enum: `'owner' \| 'member'`, default `'member'` for invited users, `'owner'` for self-provisioned tenants |

> One user still belongs to exactly one tenant. The change is that a tenant can have many users, and one of them is flagged as the owner. A partial unique index enforces "at most one owner per tenant": `CREATE UNIQUE INDEX ON users (tenant_id) WHERE role = 'owner'`.

### New: `invitations` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants NOT NULL | tenant being shared |
| `email` | TEXT NOT NULL | normalised lowercase |
| `invited_by_user_id` | UUID FK → users NOT NULL | for display in the UI |
| `token` | TEXT UNIQUE NOT NULL | unguessable secret embedded in invite link |
| `status` | TEXT NOT NULL | `'pending' \| 'accepted' \| 'revoked' \| 'expired'`, default `'pending'` |
| `expires_at` | TIMESTAMPTZ NOT NULL | default `created_at + 14 days` |
| `accepted_at` | TIMESTAMPTZ | set when redeemed |
| `accepted_by_user_id` | UUID FK → users | set when redeemed |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

A partial unique index on `(tenant_id, lower(email)) WHERE status = 'pending'` prevents duplicate live invitations to the same address.

### Tenants table

No structural change. The existing `slug` and seed columns remain.

---

## Backend Changes

### Tenant Resolution (PRD 016 → updated)

The auto-provisioning logic in `middleware/tenant.py` becomes:

1. Look up `User` by `clerk_user_id`. If found → return their `tenant_id`.
2. If not found, look for a **pending invitation** matching the user's verified Clerk email.
   - Match: create a `User` attached to the invitation's `tenant_id` with `role = 'member'`, mark the invitation `accepted`, return that `tenant_id`.
3. Otherwise: existing behaviour — create a new `Tenant` and a `User` with `role = 'owner'`.

This keeps the solo onboarding path identical and makes invitation redemption a side effect of normal sign-in. No separate "accept invite" page is strictly required for v1; the email link simply deep-links to Clerk sign-in pre-filled with the invited email, and the next API call resolves the invitation.

### New Endpoints

All endpoints below require Clerk JWT auth (PRD 016) and operate within the caller's tenant.

| Method | Path | Caller role | Purpose |
|---|---|---|---|
| `GET` | `/api/team/members` | any | list users in the tenant (id, email, github_username, role, created_at) |
| `GET` | `/api/team/invitations` | owner | list pending invitations |
| `POST` | `/api/team/invitations` | owner | create an invitation `{email}` → sends email, returns invitation row |
| `DELETE` | `/api/team/invitations/{id}` | owner | revoke a pending invitation |
| `POST` | `/api/team/invitations/{id}/resend` | owner | re-send the invitation email (no token rotation) |
| `DELETE` | `/api/team/members/{user_id}` | owner | remove a member from the tenant |
| `POST` | `/api/team/transfer-ownership` | owner | `{new_owner_user_id}` — atomically swap the owner role |

Authorization is enforced by a `require_owner` dependency that asserts `current_user.role == 'owner'`. Member-targeted endpoints additionally reject self-removal and removal of the current owner (must transfer first).

### Removing a Member

Deleting the `users` row is sufficient — the user retains their Clerk identity but on next sign-in step 1 fails, step 2 finds no invitation, and step 3 provisions them a fresh empty tenant. This matches the principle of least surprise (they aren't locked out of Distilled, just out of the previous tenant) and avoids needing a "you've been removed" screen for v1.

### Transferring Ownership

Single transaction:
```sql
UPDATE users SET role = 'member' WHERE id = :current_owner_id;
UPDATE users SET role = 'owner'  WHERE id = :new_owner_id AND tenant_id = :tenant_id;
```
The partial unique index guarantees only one owner exists at any time; the transaction ordering must demote first, then promote, to respect the constraint.

### Email Delivery

Invitation emails are sent through Clerk's transactional email API or a lightweight provider (Resend / Postmark). Email content:

- Subject: `<Owner name> invited you to <Tenant name> on Distilled`
- Body: short, on-brand, dark-themed HTML with a single CTA linking to `https://<app>/invite?token=<token>`.
- The link resolves to a Clerk sign-in page; the token is exchanged server-side after authentication completes.

---

## Frontend Changes

### Settings → Team Page

A new screen under the existing settings area, accessible to all members but with management controls visible only to the owner.

```
┌──────────────────────────────────────────────────────────┐
│  Team                                                    │
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
└──────────────────────────────────────────────────────────┘
```

- The `[⋯]` menu (owner-only) offers **Remove** and **Transfer ownership**. Both require a confirmation dialog naming the affected member.
- For non-owners, the page is read-only: they see the list and roles but no action menus or invite button.
- Empty pending invitations list collapses to nothing — no empty-state card.

### Invite Modal

Single email field with inline validation. Submits to `POST /api/team/invitations`. On success, the modal closes and the new row appears in the pending list. Errors (duplicate pending invite, already a member, malformed email) render below the field.

### Sign-In via Invitation

No new page needed. The invited email link routes the user through Clerk's existing sign-in. The first authenticated API call invokes the updated tenant resolver, which redeems the invitation transparently. The user lands on the shared dashboard.

A small one-time toast — `Welcome to <Tenant name>` — appears on first load after redemption to confirm they're in the right place.

### Header / Account Menu

The existing user menu gains a single line: the tenant name, with a dimmer "Owner" or "Member" label underneath. No tenant switcher (out of scope).

---

## Edge Cases & Behaviour

- **Invitee already has a Distilled tenant of their own.** Reject the invitation acceptance. We don't move users between tenants in v1; the invitee must contact support or accept that their existing tenant takes precedence. Surface this clearly in the email-link landing page: "You already have a Distilled account. Multi-tenant membership isn't supported yet."
- **Owner tries to remove themselves.** Blocked by API; UI hides the option. Must transfer ownership first.
- **Owner tries to transfer to a non-member.** Blocked. Transfer target must already be a member of the tenant.
- **Invitation expires.** `status` flips to `'expired'` via a periodic job (or lazily on read). The owner can re-issue from the team page.
- **Invitation revoked after sign-in but before first API call.** Race is acceptable: the redeem-on-resolve step reads `status = 'pending'` under a row lock; if it's been revoked, the user falls through to step 3 and gets a fresh tenant. No data leaks.
- **GitHub App installation context.** The installation remains tenant-scoped. Members do not need to re-install or re-authorise the GitHub App — they inherit access through tenant membership.

---

## Acceptance Criteria

### Membership
- [ ] A tenant created via solo sign-up has exactly one user, role `owner`.
- [ ] A tenant can have at least 10 members in addition to the owner without performance regression on dashboard load.
- [ ] All members see identical data via the dashboard and API.
- [ ] At most one user per tenant has `role = 'owner'` at any time (DB constraint enforced).

### Invitations
- [ ] An owner can invite a teammate by email; the teammate receives an email with a working link within 30 seconds.
- [ ] A non-owner cannot create, revoke, or resend invitations (API returns 403; UI hides controls).
- [ ] A pending invitation cannot be created twice for the same email + tenant.
- [ ] Invitations expire after 14 days and cannot be redeemed thereafter.
- [ ] An owner can revoke a pending invitation; subsequent attempts to redeem the link fail.

### Redemption
- [ ] An invited user signs in with GitHub via Clerk and lands on the shared dashboard without seeing the onboarding/empty state.
- [ ] An invited user whose Clerk email does not match the invitation email is **not** auto-joined to the tenant.
- [ ] A solo user who already has their own tenant cannot redeem an invitation in v1; they receive a clear error.

### Removal
- [ ] An owner can remove a member; that member's next API request returns a freshly provisioned empty tenant, not the previous one.
- [ ] The owner cannot remove themselves; the API returns 400 and the UI offers transfer instead.
- [ ] A member cannot remove anyone (API 403).

### Ownership Transfer
- [ ] An owner can transfer ownership to any existing member in a single action.
- [ ] After transfer, the new owner has management rights and the old owner sees only read-only team controls.
- [ ] Ownership transfer to a non-member or non-existent user fails with 400.
- [ ] At no point during transfer does the tenant have zero or two owners.

---

## Open Questions

1. **Cross-tenant membership.** We're explicitly forbidding it in v1, which forces invitees who are already Distilled users into a dead end. Is the "contact support" fallback acceptable, or should we offer a "leave my current tenant and join this one" action? The latter doubles the surface area but unblocks a real case (an EM who tried Distilled solo before their CTO did).

2. **Member-initiated leaving.** Should a non-owner be able to leave a tenant on their own (without owner action)? Symmetric to removal; trivial to add. Worth doing for v1 or defer?

3. **Invitation email branding & sender.** Send from `noreply@distilled.<tld>` via Resend/Postmark, or rely on Clerk's built-in invitation emails? Clerk's flow is faster to ship but couples our membership model to Clerk's invitation primitive, which we'd later want to detangle.

4. **Tenant naming.** Today the tenant `slug` derives from the owner's GitHub username (PRD 016). Once a tenant is multi-user, that's a confusing artifact ("acme-eng's tenant" but Anna left). Should the owner be able to rename the tenant from the team page? Out of scope here, but called out for sequencing.

5. **Audit trail.** No logging of "who invited / removed / transferred" beyond `invited_by_user_id`. Acceptable for v1, or do we need a minimal `tenant_audit_log` table now to avoid a backfill later?
