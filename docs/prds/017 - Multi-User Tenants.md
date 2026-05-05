# Multi-User Tenants & Account Sharing

## Summary

Allow more than one user to access the same Distilled tenant, and allow a single user to belong to more than one tenant. Today every Clerk user is provisioned their own private tenant with no path to share it — engineering leaders cannot bring their team into the product without handing over credentials. This PRD introduces an explicit owner role on each tenant, an invitation flow for adding teammates (over GitHub-only sign-in), a tenant switcher for users with access to multiple workspaces, and the ability to remove members, transfer ownership, or leave a tenant. It also folds in the small set of changes needed to make the solo → team transition feel intentional: renaming the tenant when you invite your first teammate, and leaving (or deleting) a solo tenant once your team's "official" tenant exists.

---

## Problem

PRD 016 established a 1:1 mapping between Clerk users and tenants — a tenant is created at first login and is permanently associated with that one user. This was the right shape for solo onboarding, but it has four concrete consequences that block real customer use:

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
5. Let members leave a tenant at any time. Let an owner delete a tenant when they are its sole user. Owners who have other members cannot leave — they must transfer ownership first.
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
- Tenant deletion as a general feature. The narrow case of "owner is the only user" is supported via an explicit Delete tenant action; broader tenant lifecycle management is deferred.

---

## Users

**Primary (owner):** The engineering leader who signed up first and "owns" the Distilled account for their company. They want to bring in their EMs and direct reports without re-onboarding the data.

**Secondary (member):** An EM, staff engineer, or peer leader invited by the owner. They authenticate with their own GitHub account via Clerk and land directly in the shared tenant — no setup, no GitHub App install, no empty state.

**Tertiary (returning solo user):** Someone who tried Distilled before their company adopted it, has a personal tenant, and is now invited to the company tenant. They need to be able to switch between both, and to leave or delete their personal one if they choose.

**Journey (owner):** dashboard → "Settings → Team" → invite first teammate → prompted to rename tenant from "Anna's tenant" to "Acme Engineering" → invite sent. Later: remove a member, or transfer ownership before leaving the company.

**Journey (member):** receive invitation email → click link → sign in with GitHub via Clerk → land on the shared dashboard with full data visibility. Tenant switcher in the header shows both their personal tenant (if any) and the new shared one.

---

## Concepts

### Tenant Membership

A user can belong to one or more tenants. For each tenant they belong to, they hold a role: **owner** or **member**. Every tenant has exactly one owner. Owners and members have identical read access to all tenant data. The behavioural difference is that only owners can access Settings → Team, manage membership, rename the tenant, transfer ownership, and delete the tenant.

### Active Tenant

When a user belongs to multiple tenants, the product needs to know which one they're currently looking at. The user has an **active tenant** at any given time — the dashboard, the team page, every screen scopes to that tenant. The user changes their active tenant via the tenant switcher.

On regular sign-in, the active tenant defaults to the tenant the user last used. When a user arrives via an invitation link and successfully joins a tenant, that newly joined tenant becomes the active tenant for the session.

### Invitations

An invitation is a pending grant of membership against an email address. The invited person receives an email with a unique link; clicking the link and signing in with GitHub redeems the invitation and adds them to the tenant as a member. The invitee may not have a Distilled account yet — that's fine, the act of signing in via the link both creates their account and joins them to the tenant.

The link itself is the credential. The invitee's GitHub email does not need to match the invited address. This means we can keep GitHub as the only sign-in method without forcing invitees to add a specific email to their GitHub account.

### Ownership Transfer

A tenant always has exactly one owner. Transfer is a single action: the current owner picks an existing member and promotes them; the old owner becomes a regular member. There is never a "no owner" state, and there are no co-owners.

---

## GitHub-Only Sign-In × Invitations

Sign-in remains GitHub-only via Clerk. The invite link is what authorises membership — not the email address it was sent to. So when Sam clicks the link in his email and signs in with GitHub, his GitHub account can have any email on it; we don't try to match it. Email is purely the notification channel that gets the invite to him.

For an existing Distilled user who happens to sign in normally without clicking their link, the app makes a best-effort match against the verified emails on their GitHub account and surfaces a banner — "You've been invited to Acme Engineering — Accept?" — for an explicit accept/decline. This is the only place email is used for anything beyond delivery, and it's opt-in (the user clicks Accept rather than being auto-enrolled).

---

## Workflows

### Inviting a Teammate

1. Owner opens **Settings → Team** and clicks **Invite member**.
2. If this is the first invite from a tenant whose name is still the auto-generated default, a one-time **Name your team** prompt appears before the invite modal.
3. The invite modal asks for an email address and the owner submits.
4. An invitation email is sent to the address. The pending invitation appears in the team page list.
5. The teammate clicks the link in the email, signs in with GitHub, and lands on the shared dashboard. A welcome toast confirms which tenant they've joined.

### Switching Between Tenants

A tenant switcher in the global header shows the active tenant. Users with multiple memberships click it to choose between them. For single-tenant users it renders as a static label so the chrome cost is zero. On sign-in, the active tenant defaults to the one the user last visited.

### Removing a Member

The owner opens the `[⋯]` menu next to a member and chooses **Remove**. A confirmation dialog names the member. Once confirmed, the member loses access to the tenant on their next interaction with the app. They retain any other memberships they hold.

### Leaving a Tenant

Members can leave a tenant at any time via a **Leave tenant** action on the team page. Leaving removes their access immediately and retains any other memberships they hold.

Owners do not have a "Leave" option. If they want to step back, they must transfer ownership to an existing member first, after which they become a regular member and can leave normally.

### Deleting a Tenant

An owner who is the **sole user** of a tenant can delete it via an explicit **Delete tenant** action on the team page. This is a separate, clearly destructive action — not conflated with leaving. A strong confirmation dialog names the tenant and warns that all data will be permanently deleted. On confirmation, the tenant and all its data are removed and the owner is redirected to sign-in (or their next membership, if they have one).

### Transferring Ownership

The owner opens the `[⋯]` menu next to a member and chooses **Transfer ownership**. After confirmation, that member becomes the owner and the previous owner becomes a regular member.

### Solo → Team Transition (Renaming)

When the owner clicks **Invite member** for the first time on a tenant that still has its auto-generated name (e.g. `Anna's tenant`), a one-time **Name your team** modal appears before the invite modal:

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

"Continue" renames the tenant and opens the invite modal. "Skip for now" opens the invite modal directly without renaming, and the prompt does not appear again. Owners can rename later from the team page at any time.

---

## UI / Screens

### Tenant Switcher

A compact dropdown in the top-left of the global header showing the active tenant name. Clicking it lists all tenants the user is a member of, each with a role badge.

### Settings → Team Page

The team page is accessible to the **owner only**. Members do not have access to Settings.

**Owner view (with other members):**

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
└──────────────────────────────────────────────────────────┘
```

**Owner view (sole user — delete available):**

```
┌──────────────────────────────────────────────────────────┐
│  My Workspace                              [Rename]      │
│                                                          │
│  Members (1)                            [Invite member]  │
│  ──────────────────────────────────────────────────────  │
│  Anna Chen           anna@acme.com       Owner           │
│                                                          │
│  ──────────────────────────────────────────────────────  │
│  [Delete tenant]                                         │
└──────────────────────────────────────────────────────────┘
```

- The `[⋯]` menu offers **Remove** and **Transfer ownership** for each member.
- **Delete tenant** is only shown when the owner is the sole user. A strong confirmation dialog names the tenant and warns that all data will be permanently deleted.
- There is no "Leave tenant" option for owners. To step back, the owner must transfer ownership first.

### Invite Modal

A single email field:

```
┌──────────────────────────────────────────────┐
│  Invite a teammate                           │
│                                              │
│  Email address                               │
│  [ sam@acme.com                          ]   │
│                                              │
│                       [Cancel] [Send invite] │
└──────────────────────────────────────────────┘
```

### Pending Invitation Banner

For existing Distilled users who sign in without clicking the invite link, a dismissable banner appears at the top of the dashboard if their verified GitHub emails match a pending invitation:

```
┌─────────────────────────────────────────────────────────┐
│  You've been invited to Acme Engineering.               │
│                              [Decline]  [Join tenant →] │
└─────────────────────────────────────────────────────────┘
```

### Header / Account Menu

A "Member" or "Owner" badge appears for the active tenant. The tenant name itself lives in the tenant switcher.

---

## Email

Invitation emails are sent through a dedicated transactional provider, decoupled from Clerk. Clerk's invitation primitive is too tightly coupled to its own user model and does not extend cleanly to future product comms (billing receipts, digest emails, etc.). The exact provider is an implementation detail for the RFC.

Email content:
- **Subject:** `<Owner name> invited you to <Tenant name> on Distilled`
- **Body:** short, on-brand, dark-themed HTML with a single CTA to accept the invitation.

---

## Documentation

The following docs must land alongside the implementation:

- **Getting Started guide** (new): a short walkthrough covering sign-in, the solo → team transition (including the rename prompt), inviting teammates, switching between tenants, and the path for "I tried Distilled solo and just got invited to my company's tenant" — including how to leave or delete a personal tenant.
- **Architecture documentation:** updates to reflect the multi-tenant membership model.
- **ADR:** a short ADR documenting the move from one-user-per-tenant to many-users-per-tenant-and-many-tenants-per-user, so future contributors don't trip on the PRD-016 1:1 assumption.

---

## Edge Cases & Behaviour

- **Invitee already has a Distilled tenant of their own.** Allowed — they gain a second membership and can switch between tenants. The newly accepted tenant becomes their active tenant on first sign-in after redemption.
- **Owner tries to remove themselves.** Not allowed via Remove. Owners must transfer ownership to step back from the role, or use Delete tenant if they are the sole user.
- **Owner tries to transfer to a non-member.** Not allowed. Transfer target must already be a member of the tenant.
- **Owner is the sole user and deletes the tenant.** The tenant and all its data are permanently deleted after a strong confirmation. The owner is redirected to sign-in (or their next membership if they have one). There is no undo.
- **Invitation expires.** Invitations expire after 14 days. The link returns an expired-invite page; the owner can re-issue from the team page.
- **Invitation revoked after the invitee has clicked but before they've completed sign-in.** The redemption fails gracefully — no membership is created. No data leaks.
- **Invitee doesn't click the link.** If they sign in directly, the pending-invitation banner appears when their verified GitHub emails include the invited address. If they have a completely different email on GitHub, neither auto-redemption nor the banner fires — the owner should resend the link for the invitee to click directly.
- **GitHub App installation context.** The installation remains tenant-scoped. Members do not need to re-install or re-authorise the GitHub App — they inherit access through tenant membership.
- **Two tabs, two tenants.** A power user should be able to keep one tab on each tenant they belong to without one tab's actions clobbering the other's view.

---

## Acceptance Criteria

### Membership
- [ ] A tenant created via solo sign-up has exactly one user, an owner.
- [ ] A tenant can have at least 10 members in addition to the owner without performance regression on dashboard load.
- [ ] All members see identical data via the dashboard.
- [ ] A tenant always has exactly one owner.
- [ ] A user can be a member of multiple tenants simultaneously.

### Invitations
- [ ] An owner can invite a teammate by email; the teammate receives an email within 30 seconds containing a unique invite link.
- [ ] Clicking the invite link, signing in with any GitHub account, and completing the OAuth flow redeems the invitation and lands the user on the shared dashboard regardless of which email is on their GitHub account.
- [ ] An existing Distilled user who signs in without the link sees a pending-invitation banner when their verified GitHub emails match the invited address.
- [ ] Accepting via the banner creates the membership; declining dismisses it without creating one.
- [ ] A non-owner cannot create, revoke, or resend invitations (UI hides controls).
- [ ] A pending invitation cannot be created twice for the same email + tenant.
- [ ] Invitations expire after 14 days.
- [ ] An owner can revoke a pending invitation; subsequent attempts to redeem the link show an invalid-invite page.

### Tenant Switching
- [ ] A user with multiple memberships sees all of them in the tenant switcher.
- [ ] Selecting a tenant in the switcher reloads the dashboard against that tenant's data.
- [ ] On sign-in, the active tenant defaults to the tenant the user last visited.
- [ ] When a user joins via an invite link, the newly joined tenant is set as the active tenant for that session.
- [ ] Two browser tabs scoped to two different tenants do not interfere with each other.
- [ ] A user cannot access a tenant they're not a member of.

### Removal & Leaving
- [ ] An owner can remove a member; that member loses access on their next interaction, while retaining any other memberships.
- [ ] A member can leave a tenant on their own via the Leave tenant action on the team page.
- [ ] Owners have no "Leave tenant" option; the Settings → Team page does not show one.
- [ ] An owner who is the sole user of a tenant can delete it via an explicit Delete tenant action; the tenant and all its data are permanently removed.

### Ownership Transfer
- [ ] An owner can transfer ownership to any existing member in a single action.
- [ ] After transfer, the new owner has full management rights and the old owner loses access to Settings → Team.
- [ ] Ownership cannot be transferred to a non-member.
- [ ] A tenant never has zero or two owners during transfer.

### Solo → Team Transition
- [ ] On the first invite from a tenant whose name is still the auto-generated default, the rename prompt appears.
- [ ] Skipping the rename prompt does not block the invite, and the prompt does not appear again on subsequent invites.
- [ ] An owner can rename the tenant from the team page at any time.

### Local Development
- [ ] Seed data exercises multi-tenant flows end-to-end (multiple tenants, users with mixed memberships, at least one pending invitation).

