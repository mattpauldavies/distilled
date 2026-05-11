# RFC 021: Multi-User Tenants & Account Sharing

## Summary

Replace the 1:1 user → tenant relationship established in RFC 016 with a many-to-many membership model. Each tenant gains a single **owner** and zero-or-more **members**. Owners can invite teammates by email, remove members, transfer ownership, rename the tenant, or delete it when they are the sole user. A user may belong to multiple tenants and switches between them via a header dropdown. Sign-in remains GitHub-only via Clerk; invitations are redeemed by clicking a tokenised link, so the GitHub email on the invitee's account need not match the address the invite was sent to.

The four pillars: a `tenant_users` join table replaces `users.tenant_id` as the source of truth; an `invitations` table backs the invite/redeem flow; per-request **active tenant** resolution via an `X-Tenant-Id` header lets a single Clerk session drive multiple tenant contexts; a transactional email provider (Resend) is introduced for invitation delivery, decoupled from Clerk.

---

## Context

Today (post RFC 016):

- `server/app/models/user.py` — `User.tenant_id` is a NOT-NULL FK to `tenants.id`. Each user belongs to exactly one tenant.
- `server/app/auth.py` — `require_auth` resolves `(user, tenant)` from the JWT `sub`, returning a `CurrentUser(user_id, tenant_id, clerk_user_id)`.
- `server/app/services/user_service.py:get_or_create_user_and_tenant` — first-login provisioning creates a `Tenant` + `User` in one transaction and treats that user as the implicit owner.
- `server/app/middleware/tenant.py:get_tenant_id` — derives `tenant_id` from `CurrentUser`. Every protected route depends on this.
- `server/app/services/installation_service.py` — matches GitHub App installs to tenants by `User.github_account_id`.

The data model is multi-tenant by row (every domain table has `tenant_id`), but the access model is single-tenant by user. This RFC keeps the row model and rewires the access model around memberships.

---

## Decisions

The PRD raised several implementation questions; the resolutions are:

1. **Membership model** → a dedicated `tenant_users` table with `(user_id, tenant_id, role)`. `users.tenant_id` is dropped.
2. **Active tenant transport** → client sends `X-Tenant-Id` on every authenticated request. Membership is verified server-side per request. The user's *last active* tenant is persisted to `users.last_active_tenant_id` for sign-in defaulting and survives across sessions and devices.
3. **Invitation token** → opaque 32-byte URL-safe token, stored hashed (SHA-256) in `invitations.token_hash`. The raw token only exists in the email link.
4. **Email provider** → Resend, abstracted behind a small `EmailService` interface so we can swap providers later without touching invitation logic.
5. **Tenant deletion cascade** → all FK references to `tenants.id` get `ON DELETE CASCADE`. Deletion is implemented as a single SQL statement; no per-table fan-out.
6. **Existing solo users** → migrated automatically: each existing `users.tenant_id` becomes an `owner` membership in the new table. No user-visible change on first deploy.
7. **Email-to-invitation matching for the banner** → backend fetches verified GitHub email addresses for the current user from the Clerk Backend API on demand, and matches against pending invitations.
8. **GitHub App installation** → installation remains tenant-scoped; no changes. Members of a tenant inherit access through their membership and the tenant's existing installation row.

---

## Concepts

### Membership

A user's relationship to a tenant is a row in `tenant_users`. The role is `owner` or `member`. A tenant has **exactly one** owner row at all times — enforced by a partial unique index. The previous semantic of "the user who owns the tenant" lives in this row, not on the tenant or the user.

### Active Tenant

The "active tenant" is request-scoped: each authenticated request carries `X-Tenant-Id`, the backend verifies membership, and routes operate in that tenant's scope. The user's `last_active_tenant_id` column is the durable default used when no header is provided (e.g. immediately after sign-in, before the client has a tenant in hand). This design supports two-tabs-two-tenants naturally: each tab simply sends a different header.

### Invitation

A pending grant of membership against an email address. Carries a unique opaque token (the link is the credential). Redemption requires being signed in with any GitHub account; the invitee's email need not match. Invitations expire after 14 days.

### Solo → Team Transition

The first invite from a tenant whose name was auto-generated triggers a one-time **Name your team** prompt (see PRD). Tracked by a boolean `tenants.rename_prompt_dismissed`. The existing `slug` is left untouched; only `name` is editable.

---

## Data Model Changes

### New: `tenant_users` table

```python
class TenantUser(TimestampMixin, Base):
    __tablename__ = "tenant_users"

    id: UUID PK
    tenant_id: UUID FK → tenants.id ON DELETE CASCADE
    user_id: UUID FK → users.id ON DELETE CASCADE
    role: TEXT NOT NULL CHECK (role IN ('owner','member'))

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_users_tenant_user"),
        # Exactly one owner per tenant
        Index(
            "uq_tenant_users_one_owner",
            "tenant_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )
```

### New: `invitations` table

```python
class Invitation(TimestampMixin, Base):
    __tablename__ = "invitations"

    id: UUID PK
    tenant_id: UUID FK → tenants.id ON DELETE CASCADE
    invited_by_user_id: UUID FK → users.id ON DELETE SET NULL
    email: CITEXT NOT NULL              # case-insensitive match
    token_hash: TEXT NOT NULL UNIQUE    # SHA-256 of the URL token
    expires_at: TIMESTAMPTZ NOT NULL
    redeemed_at: TIMESTAMPTZ NULL
    revoked_at: TIMESTAMPTZ NULL

    __table_args__ = (
        # At most one open invitation per (tenant, email)
        Index(
            "uq_invitations_open_tenant_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("redeemed_at IS NULL AND revoked_at IS NULL"),
        ),
    )
```

`citext` keeps `Sam@Acme.com` and `sam@acme.com` interchangeable. The extension is enabled in the same migration.

### Modified: `users` table

```sql
ALTER TABLE users ADD COLUMN last_active_tenant_id UUID
    REFERENCES tenants(id) ON DELETE SET NULL;
ALTER TABLE users DROP COLUMN tenant_id;
```

The `users.tenant_id` column is removed once memberships are backfilled. Going forward, "what tenant is this user looking at?" is answered by `X-Tenant-Id` (per request) or `last_active_tenant_id` (default).

### Modified: `tenants` table

```sql
ALTER TABLE tenants ADD COLUMN rename_prompt_dismissed BOOLEAN NOT NULL DEFAULT FALSE;
```

### Cascade FKs

All existing tenant-scoped tables get `ON DELETE CASCADE` on their `tenant_id` FK so tenant deletion is a single statement. Tables touched: `repositories`, `github_installations`, `production_deployment_events`, `pull_requests`, `environments`, `deployment_attributions`, `metrics_*`, `webhook_events`.

### Migration

A single Alembic revision `multi_user_tenants` does the full transition atomically (migrations run inline with code deploy, so a split rollout buys nothing):

- Enable `citext` extension
- Create `tenant_users` and `invitations`
- Add `users.last_active_tenant_id` (nullable)
- Add `tenants.rename_prompt_dismissed` (default FALSE)
- Backfill: `INSERT INTO tenant_users (id, tenant_id, user_id, role) SELECT gen_random_uuid(), tenant_id, id, 'owner' FROM users;`
- Backfill: `UPDATE users SET last_active_tenant_id = tenant_id;`
- Drop `users.tenant_id`
- Recreate tenant-scoped FKs with `ON DELETE CASCADE`

---

## Architecture

### Request Flow (authenticated)

```
Browser                  FastAPI
  │                         │
  │── GET /api/repos        │
  │   Authorization: Bearer <jwt>
  │   X-Tenant-Id: <uuid>   │
  │────────────────────────►│
  │              verify JWT (Clerk)
  │              load User by clerk_user_id
  │              verify TenantUser(user, tenant) exists
  │              update users.last_active_tenant_id (async, fire-and-forget)
  │              dispatch route with CurrentUser{user, tenant, role}
  │◄─────────── 200 ────────│
```

If the header is absent, the backend falls back to `users.last_active_tenant_id`. If neither is available (brand-new user pre-onboarding, or all memberships removed), routes that depend on `get_tenant_id` return 409 `no_active_tenant`, which the client handles by routing to the onboarding/no-tenant screen.

If the header names a tenant the user is not a member of, the backend returns 403 `not_a_member`. The client clears the stale tenant and falls back to the user's first available membership or the no-tenant screen.

### Email Service

```python
class EmailService(Protocol):
    async def send_invitation(
        self,
        *,
        to: str,
        tenant_name: str,
        inviter_name: str,
        accept_url: str,
    ) -> None: ...
```

Implementations:
- `ResendEmailService` — production, posts to `https://api.resend.com/emails`
- `LoggingEmailService` — local dev / tests, logs the rendered HTML and accept URL

Selected at startup based on `EMAIL_PROVIDER` env (`resend` | `log`). Templates are inline HTML strings; we don't introduce a templating engine for one email.

---

## Backend Changes

### 1. `app/models/`

- New: `tenant_membership.py`, `invitation.py`
- Modify: `user.py` — drop `tenant_id`, add `last_active_tenant_id`
- Modify: `tenant.py` — add `rename_prompt_dismissed`
- Update `app/models/__init__.py` exports

### 2. `app/auth.py` and `app/middleware/tenant.py`

`CurrentUser` gains `role` and is now resolved against an active tenant header:

```python
@dataclass
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Literal["owner", "member"]
    clerk_user_id: str

async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser: ...

async def require_owner(current: CurrentUser = Depends(require_auth)) -> CurrentUser:
    if current.role != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    return current
```

`get_tenant_id` continues to delegate to `require_auth` — no per-route changes for read-side endpoints.

### 3. `app/services/user_service.py`

Rewrite `get_or_create_user_and_tenant` to:
- Look up `User` by `clerk_user_id`
- If absent → create `Tenant` + `User` + `TenantUser(role='owner')` in one transaction; set `users.last_active_tenant_id = tenant.id`
- If present → resolve active tenant from `X-Tenant-Id` header (preferred) or `last_active_tenant_id` (fallback); verify membership exists; return `(user, tenant, role)`

A new helper updates `last_active_tenant_id` lazily (only writes when value changes).

### 4. New: `app/services/membership_service.py`

```python
async def list_memberships(user_id, session) -> list[MembershipView]
async def add_member(tenant_id, user_id, role, session) -> TenantUser
async def remove_member(tenant_id, user_id, session) -> None
async def transfer_ownership(tenant_id, current_owner_id, new_owner_id, session) -> None
async def leave_tenant(tenant_id, user_id, session) -> None  # fails for owners
async def delete_tenant(tenant_id, session) -> None          # fails if >1 member
async def rename_tenant(tenant_id, name, session) -> Tenant
async def dismiss_rename_prompt(tenant_id, session) -> None
```

Ownership transfer runs as a single transaction: demote current owner to member, promote target member to owner. The partial unique index on `(tenant_id) WHERE role='owner'` enforces invariant safety against races.

### 5. New: `app/services/invitation_service.py`

```python
async def create_invitation(tenant_id, inviter_user_id, email, session) -> Invitation
async def revoke_invitation(invitation_id, session) -> None
async def resend_invitation(invitation_id, session) -> Invitation  # new token, new expiry
async def redeem_invitation(token, current_user_id, session) -> Tenant
async def list_pending_for_tenant(tenant_id, session) -> list[Invitation]
async def list_pending_for_user_emails(user_id, emails, session) -> list[Invitation]
async def expire_old_invitations(session) -> int  # for scheduled job
```

`create_invitation` rejects duplicates against the partial unique index, generates `secrets.token_urlsafe(32)`, hashes with `hashlib.sha256`, persists, and dispatches the email.

`redeem_invitation` is the only path that creates a non-self-provisioned membership. It:
- Validates the token (lookup by `sha256(token)`)
- Checks not expired, not revoked, not already redeemed
- Inserts a `tenant_users` row with role `member` (idempotent on `(tenant_id, user_id)`)
- Marks invitation `redeemed_at = now()`
- Sets `users.last_active_tenant_id = tenant_id`

### 6. New: `app/services/email_service.py`

`EmailService` Protocol + `ResendEmailService` + `LoggingEmailService` as described above. The accept URL is built from `APP_BASE_URL` + `/invitations/accept?token=<raw>`.

### 7. New: `app/routes/team.py`

Mounted at `/team`, all routes depend on `require_owner` except where noted.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/team` | List members + pending invitations for active tenant | `require_owner` |
| PATCH | `/team` | Rename tenant; dismiss rename prompt | `require_owner` |
| POST | `/team/invitations` | Create invitation | `require_owner` |
| POST | `/team/invitations/{id}/resend` | Re-issue token + email | `require_owner` |
| DELETE | `/team/invitations/{id}` | Revoke pending invitation | `require_owner` |
| DELETE | `/team/members/{user_id}` | Remove member | `require_owner` |
| POST | `/team/members/{user_id}/transfer` | Transfer ownership to member | `require_owner` |
| POST | `/team/leave` | Leave tenant (members only; 403 for owners) | `require_auth` |
| DELETE | `/team` | Delete tenant (sole-user owner only) | `require_owner` |

### 8. New: `app/routes/me.py`

Tenant-agnostic — depends only on the JWT, not on `X-Tenant-Id`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/me/tenants` | All memberships for the current user, with role + tenant name |
| GET | `/me/invitations` | Pending invitations matching the user's verified GitHub emails |
| POST | `/me/invitations/{id}/accept` | Accept a pending invitation matched via the banner |
| POST | `/me/invitations/{id}/decline` | Mark dismissed (deletes the row for that user — token still valid for direct redeem if not revoked) |
| POST | `/me/active-tenant` | Set `users.last_active_tenant_id` (after switcher selection) |

`POST /me/invitations/{id}/accept` validates that one of the user's verified GitHub emails matches the invitation's email before creating the membership — this is the email-based codepath, distinct from token redemption.

### 9. New: `app/routes/invitations.py` (no `X-Tenant-Id`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/invitations/redeem` | Body: `{ token }`. Requires JWT. Redeems, returns the joined tenant. |

There is no preview endpoint. The user has already read the inviter's name and the tenant name in the email; re-displaying them in-app before sign-in adds a confirmation step without value. The redeem call is fired automatically once the user is signed in (see frontend §8) and the joined tenant's name is surfaced in a welcome toast — that's the first time the app speaks to the user about which tenant they've joined.

### 10. `app/services/clerk_service.py`

Add a helper to fetch verified email addresses:

```python
async def get_user_emails(self, clerk_user_id: str) -> list[str]:
    """Returns verified email addresses (lower-cased)."""
```

Used by `/me/invitations` to match verified emails against pending invitations.

### 11. `app/services/installation_service.py`

No structural change. The match-by-`github_account_id` logic continues to work because each tenant still has exactly one owner whose GitHub account ID identifies the install. (If we later want non-owners to install GitHub Apps onto the tenant, that's a separate RFC.)

### 12. Scheduled jobs

Add an internal endpoint `POST /internal/invitations/expire` (auth: `internal_cron_secret`) that nulls expired invitations. Wire into Railway's scheduler. The expiry check is also enforced inline at redeem time, so the scheduler is a janitor, not a correctness mechanism.

### 13. Config additions (`app/config.py`)

| Field | Default | Notes |
|---|---|---|
| `app_base_url` | `""` | Public URL of the frontend; used for invite accept links |
| `email_provider` | `"log"` | `"resend"` in prod |
| `resend_api_key` | `""` | Required when `email_provider == "resend"` |
| `email_from` | `""` | e.g. `Distilled <invites@distilled.app>` |
| `invitation_ttl_days` | `14` | Per PRD |

`_validate_production_secrets` extended to require `resend_api_key`, `email_from`, and `app_base_url` when `environment == "production"`.

---

## Frontend Changes

### 1. New types (`client/src/types/team.ts`)

```ts
export type Role = "owner" | "member"

export interface TenantSummary {
  id: string
  name: string
  slug: string | null
  role: Role
}

export interface Member {
  user_id: string
  email: string | null
  github_username: string | null
  role: Role
}

export interface PendingInvitation {
  id: string
  email: string
  invited_at: string
  expires_at: string
}
```

### 2. Active-tenant context (`client/src/lib/tenantContext.tsx`)

A React context exposing `{ activeTenant, setActiveTenant, memberships }`. Sourced from `GET /me/tenants` on mount. The selected tenant is mirrored to `localStorage` (per-origin) so a refresh keeps the same tab on the same tenant; cross-tab independence is preserved by reading `localStorage` only on initial mount, not subscribing to `storage` events.

### 3. `client/src/lib/api.ts` — attach `X-Tenant-Id`

```ts
export function makeApiFetch(
  getToken: () => Promise<string | null>,
  getTenantId: () => string | null,
) {
  return async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
    const [token, tenantId] = [await getToken(), getTenantId()]
    return fetch(`${API_BASE}${input}`, {
      ...init,
      headers: {
        ...init?.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(tenantId ? { "X-Tenant-Id": tenantId } : {}),
      },
    })
  }
}
```

A small wrapper hook `useApiFetch()` reads from both `useAuth()` and the tenant context so call sites stay one-liners.

All existing hooks (`useRepos`, `useDashboard`, `useDataQuality`, `usePRAgeing`, etc.) switch to `useApiFetch()` — a mechanical change.

### 4. New: `client/src/components/TenantSwitcher.tsx`

Dropdown rendered in the global header. Shows the active tenant name; opens a list of all memberships with role badges. Selecting a tenant calls `setActiveTenant`, which updates context, calls `POST /me/active-tenant` (fire-and-forget), and triggers a refetch of dashboard data. For users with one membership, renders a static label (no dropdown chrome).

### 5. New: `client/src/components/team/TeamPage.tsx`

Owner-only page (members get a 403; the route guards by checking `activeTenant.role === "owner"` and falling back to the dashboard). Implements:

- Tenant rename inline editor
- Members list with `[⋯]` menu (Remove, Transfer ownership)
- Pending invitations list with Resend / Revoke
- `Invite member` button → opens `<InviteMemberModal />`
- `Delete tenant` button — visible only when `members.length === 1`
- Strong confirm dialogs for: remove, transfer, revoke, leave, delete

### 6. New: `client/src/components/team/InviteMemberModal.tsx`

If `tenant.rename_prompt_dismissed === false` and the tenant name still equals the auto-generated default (compared client-side to `tenant.slug`-derived name), the modal first renders the **Name your team** step. "Continue" calls `PATCH /team` to set both `name` and `rename_prompt_dismissed = true`, then advances to the email step. "Skip for now" calls `PATCH /team` with `rename_prompt_dismissed = true` only, then advances. Subsequent invites skip step 1.

### 7. New: `client/src/components/InvitationBanner.tsx`

Mounted in `<Dashboard />`. On mount calls `GET /me/invitations`. If non-empty, renders the dismissable banner with Accept / Decline. Accept → `POST /me/invitations/{id}/accept` → switch active tenant to the joined one.

### 8. New: `client/src/pages/AcceptInvitePage.tsx` and routing

A new route `/invitations/accept?token=<raw>` mounted **before** the Clerk gate. Redemption is bundled into the first sign-in — the user clicks the email link, signs in with GitHub, and lands in the joined tenant. There is no intermediate confirm step, no preview of the tenant name, and no extra button. Behaviour:

- If signed out: render a centred loading card and the Clerk `<SignIn>` widget with `redirectUrl=/invitations/accept?token=<raw>` so we return here after auth.
- If signed in: immediately `POST /invitations/redeem` with the token. On success: switch active tenant to the joined one, redirect to `/`, and surface a `Welcome to <tenant name>` toast on the dashboard.
- On error (expired / revoked / already redeemed): render an inline error state with a single CTA back to the dashboard. The user can ask the owner to re-issue.

This is the first non-dashboard route in the app, so we wire `react-router` (or a minimal hash-route check — to be decided in implementation) and update `App.tsx` to dispatch. The token is held in component state only — never persisted to `localStorage` or query strings on the dashboard — so a successful redemption leaves no trace in the user's URL bar after redirect.

### 9. New: `client/src/components/SignOutButton.tsx`

Already exists; extend the header to include the `<TenantSwitcher />` next to it.

### 10. Member-vs-owner UI

`activeTenant.role` is the single source of truth:
- Owner sees a "Settings" / "Team" link in the header.
- Member does not see Settings, sees only the dashboard and the tenant switcher.

---

## Email Template

Single inline-HTML template, dark-themed, rendered server-side in `ResendEmailService`. Subject: `<Inviter> invited you to <Tenant> on Distilled`. Single CTA button to the accept URL. No tracking pixels, no marketing copy. Plaintext fallback included.

---

## Documentation

- **`docs/getting-started.md`** (new) — covers sign-in, solo onboarding, inviting teammates, tenant switching, leaving, deleting a personal tenant after joining a company tenant.
- **`docs/architecture.md`** — update the "Multi-tenancy" section to describe memberships, active-tenant header, and ownership invariants.
- **`docs/adrs/002-multi-user-tenancy.md`** (new) — short ADR documenting the move from `users.tenant_id` to `tenant_users`, the `X-Tenant-Id` header decision, and the choice of Resend over Clerk-native invitations.
- **`server/README.md`** — new env vars (`APP_BASE_URL`, `EMAIL_PROVIDER`, `RESEND_API_KEY`, `EMAIL_FROM`).
- **`client/README.md`** — local dev guidance: how to set up Clerk dev users, how to use the `LoggingEmailService` accept URL printed in server logs to test invitations end-to-end without a real inbox.

---

## New Environment Variables

### Backend (`server/.env`)

| Variable | Required | Notes |
|---|---|---|
| `APP_BASE_URL` | Yes | e.g. `https://app.distilled.com` — used to construct invite accept URLs |
| `EMAIL_PROVIDER` | No | `resend` (prod) or `log` (dev). Default `log`. |
| `RESEND_API_KEY` | Prod | Required when provider is `resend` |
| `EMAIL_FROM` | Prod | RFC 5322 from address |
| `INVITATION_TTL_DAYS` | No | Default `14` |

### Frontend

No new env vars. Existing `VITE_API_BASE_URL` continues to drive the API base.

---

## Test Strategy

### Backend

- `tests/test_membership_service.py` — add member, remove member, transfer ownership (atomic), prevent owner removal, prevent transfer to non-member, prevent leave for owner with members, allow leave for member, delete-tenant only when sole user.
- `tests/test_invitation_service.py` — create + email dispatched, duplicate creation rejected, redeem (happy path), redeem (expired), redeem (revoked), redeem (already redeemed), revoke after click but before sign-in fails gracefully, expire-old-invitations job.
- `tests/test_routes_team.py` — RBAC: member is 403 on every `/team/*` route; owner gets full access. Endpoint contracts.
- `tests/test_routes_me.py` — `/me/tenants` lists all memberships; `/me/invitations` matches against verified Clerk emails (mocked); accept/decline.
- `tests/test_routes_invitations.py` — `/invitations/redeem` requires JWT; mismatch GitHub email still works (token is the credential); expired / revoked / already-redeemed paths return distinct error codes.
- `tests/test_auth.py` — `X-Tenant-Id` happy path, missing header falls back to `last_active_tenant_id`, header for non-member returns 403, header for nonexistent tenant returns 403, no active tenant returns 409, `require_owner` 403s for members.
- `tests/test_user_service.py` — first-login provisions tenant + owner membership; second login returns existing membership; switching `X-Tenant-Id` between two valid memberships does not create new rows.
- `tests/test_installation_service.py` — unchanged behaviour confirmed (regression guard).
- `tests/conftest.py` — fixtures for "tenant with one owner", "tenant with owner + member", "tenant with pending invitation". `require_auth` override now injects role.

### Frontend

- `components/TenantSwitcher.test.tsx` — single tenant renders static label; multiple tenants render dropdown; selecting a tenant updates context and calls `POST /me/active-tenant`.
- `components/team/TeamPage.test.tsx` — owner sees full controls; transfer ownership flow; remove member confirmation; delete tenant only visible at sole-user; rename inline editor.
- `components/team/InviteMemberModal.test.tsx` — first invite shows rename step; skipping persists `rename_prompt_dismissed`; subsequent invites skip rename step; duplicate email shows server validation error.
- `components/InvitationBanner.test.tsx` — fetches on mount; accept → joins tenant; decline → dismisses.
- `pages/AcceptInvitePage.test.tsx` — signed-out shows Clerk sign-in with the right `redirectUrl`; signed-in auto-redeems and routes home; expired / revoked tokens render the error state.
- `lib/tenantContext.test.tsx` — multiple tabs read independent `localStorage`; switching tenant in one context does not pollute the other.
- `hooks/useRepos.test.ts` and friends — assert `X-Tenant-Id` header is sent.

### Local development

The seed script (`server/scripts/seed_demo_data.py` or equivalent) is updated to create:
- Two tenants, each with an owner.
- A user with memberships in both tenants.
- One pending invitation against a known email.

This exercises every code path users will hit on day one.

---

## Out of Scope

- Granular roles beyond owner/member.
- Per-repo or per-metric permissions.
- Sign-in methods other than GitHub via Clerk.
- SSO / SCIM / domain-based auto-join.
- Audit logging of membership changes.
- Billing or seat limits.
- Tenant deletion as a general feature (only sole-user owner can delete).
- Migrating GitHub App installations between tenants.
- Replacing the JWKS in-process cache with shared cache (RFC 016 deferred item).

---

## Implementation Plan

### Phase 1: Data model

- [ ] **1.1** Create Alembic migration `multi_user_tenants`: enable `citext`; create `tenant_users` (with partial unique index on `role='owner'`); create `invitations` (with partial unique index on open invites); add `users.last_active_tenant_id`; add `tenants.rename_prompt_dismissed`; backfill memberships from `users.tenant_id`; backfill `last_active_tenant_id`; drop `users.tenant_id`; recreate tenant-scoped FKs with `ON DELETE CASCADE`.
- [ ] **1.2** Create `app/models/tenant_membership.py` and `app/models/invitation.py`; export from `app/models/__init__.py`.
- [ ] **1.3** Update `app/models/user.py` — add `last_active_tenant_id`, leave `tenant_id` in place for now.
- [ ] **1.4** Update `app/models/tenant.py` — add `rename_prompt_dismissed`.
- [ ] **1.5** Run migration locally; verify schema and that the backfill produced one owner row per pre-existing user.

---

### Phase 2: Auth + tenant resolution

- [ ] **2.1** Failing tests in `tests/test_auth.py` for `X-Tenant-Id` header behaviour: happy path, fallback to `last_active_tenant_id`, non-member → 403, nonexistent → 403, missing both → 409, role injected on `CurrentUser`.
- [ ] **2.2** Update `app/auth.py` — add `role` to `CurrentUser`; resolve active tenant from header → fallback; verify membership; lazily update `last_active_tenant_id`. Add `require_owner` dependency.
- [ ] **2.3** Failing tests in `tests/test_user_service.py` for: first login creates owner membership; subsequent login returns existing membership; multiple-tenant user with `X-Tenant-Id` switches correctly without new inserts.
- [ ] **2.4** Rewrite `app/services/user_service.get_or_create_user_and_tenant` to provision via `tenant_users`.
- [ ] **2.5** Update `tests/conftest.py` — fixtures for owner / member / multi-tenant user; override `require_auth` to inject role.
- [ ] **2.6** Run full server test suite — pre-existing tests pass with the membership model.

---

### Phase 3: Membership service + team routes

- [ ] **3.1** Failing tests in `tests/test_membership_service.py` covering all functions in §Backend.4.
- [ ] **3.2** Implement `app/services/membership_service.py`.
- [ ] **3.3** Failing tests in `tests/test_routes_team.py` for RBAC and endpoint contracts.
- [ ] **3.4** Implement `app/routes/team.py`; wire in `main.py` with router-level `require_auth` (per-route `require_owner` where required).

---

### Phase 4: Invitations + email

- [ ] **4.1** Implement `app/services/email_service.py` — Protocol, `LoggingEmailService`, `ResendEmailService`. Tests via the logging implementation.
- [ ] **4.2** Failing tests in `tests/test_invitation_service.py` for create / revoke / resend / redeem (all branches) / expire job.
- [ ] **4.3** Implement `app/services/invitation_service.py`.
- [ ] **4.4** Failing tests in `tests/test_routes_invitations.py` and `tests/test_routes_me.py`.
- [ ] **4.5** Implement `app/routes/me.py` and `app/routes/invitations.py`; wire in `main.py` (`/invitations/redeem` requires JWT only — does not use `X-Tenant-Id`).
- [ ] **4.6** Add Clerk `get_user_emails` helper; wire into `/me/invitations`.
- [ ] **4.7** Add `POST /internal/invitations/expire` and Railway scheduler entry.
- [ ] **4.8** Add config fields and update `_validate_production_secrets`.

---

### Phase 5: Frontend tenant context + switcher

- [ ] **5.1** Add `client/src/types/team.ts`.
- [ ] **5.2** Create `client/src/lib/tenantContext.tsx` — provider, `useActiveTenant` hook, `useMemberships` hook; mounts above `<Home />` inside `<SignedIn>`; sources from `GET /me/tenants`.
- [ ] **5.3** Update `client/src/lib/api.ts` — accept `getTenantId` argument; add `useApiFetch` hook.
- [ ] **5.4** Migrate `useRepos`, `useDataQuality`, `useDeploymentFrequency`, `useLeadTime`, `usePRCycleTime`, `useThroughput`, `useOpenPRs`, `usePRAgeing`, `useMetricSection` to `useApiFetch`. Update tests to assert `X-Tenant-Id`.
- [ ] **5.5** Build `client/src/components/TenantSwitcher.tsx` + tests; mount in `Dashboard` header next to `SignOutButton`.

---

### Phase 6: Frontend team UI

- [ ] **6.1** Build `InviteMemberModal` (with the rename step) + tests.
- [ ] **6.2** Build `TeamPage` (owner) + tests; route via in-app routing or a header link that toggles the page.
- [ ] **6.3** Build `InvitationBanner` (signed-in user with matching email) + tests; mount in `Dashboard`.
- [ ] **6.4** Build `AcceptInvitePage` + tests; introduce minimal client-side routing to handle `/invitations/accept`.
- [ ] **6.5** Hide Settings / team link for non-owners.

---

### Phase 7: Documentation + verification

- [ ] **7.1** Verify cascade locally with `DELETE FROM tenants WHERE id = '...'` against a seeded tenant; expect all dependent rows gone. Update `delete_tenant` service to use a single `DELETE` statement.
- [ ] **7.2** Write `docs/adrs/002-multi-user-tenancy.md`.
- [ ] **7.3** Update `docs/architecture.md` (multi-tenancy section).
- [ ] **7.4** Write `docs/getting-started.md`.
- [ ] **7.5** Update `server/README.md` and `client/README.md` with new env vars and dev workflow.
- [ ] **7.6** Update seed script to produce two tenants, a multi-tenant user, and a pending invitation.
- [ ] **7.7** Manual end-to-end smoke: solo sign-up → invite teammate (rename prompt) → second user redeems link with mismatched GitHub email → tenant switcher works in two tabs → owner removes member → owner transfers ownership → previous owner leaves → final user deletes tenant.
- [ ] **7.8** Full server + client test suites green.
