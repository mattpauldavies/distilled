# Getting Started

A short walkthrough for the multi-user flows. For solo onboarding without teammates, signing in is enough — Distilled provisions a personal tenant and walks you through the GitHub App install.

## Solo sign-up → adding your first teammate

1. Sign in with GitHub. Distilled creates a private tenant in your name (e.g. `anna`) and you become its **owner**.
2. Open **Settings → Team** from the dashboard header.
3. Click **Invite member**. The first time you do this on a tenant whose name is still the auto-generated default, a one-time **Name your team** prompt appears — change it to `Acme Engineering` or similar so teammates recognise it. You can skip the rename if you prefer; the prompt won't reappear.
4. Enter your teammate's email address and **Send invite**. They'll receive a link within 30 seconds.
5. Once they click the link and sign in with GitHub, they land on the same dashboard as you.

The owner role grants access to Settings → Team. Members see the dashboard only.

## Joining a team (invitee experience)

When you receive an invitation email and click the link:

- If you don't have a Distilled account yet, the page sends you to GitHub sign-in. After authenticating, you're automatically added to the inviting tenant — no second step.
- If you already have a Distilled account, the page redeems the invite against your current sign-in, again with no extra confirm step. The newly joined tenant becomes your active tenant; if you have other tenants, switch via the dropdown in the dashboard header.

The email on your GitHub account does **not** need to match the address the invite was sent to. The link itself is the credential.

If you sign in normally (without clicking the link) and your verified GitHub emails include the invited address, a banner appears at the top of the dashboard offering to accept or decline.

## Switching between tenants

A dropdown in the dashboard header shows your active tenant. If you belong to multiple tenants, click it to switch — the dashboard reloads with the chosen tenant's data. For users who belong to a single tenant, the dropdown renders as a static label (no dropdown chrome).

Two tabs can hold two different active tenants without interfering with each other; the active tenant is sent as the `X-Tenant-Id` header on every request.

## Managing your team (owner)

**Settings → Team** offers, per member:

- **Remove** — revokes the member's access on their next interaction. They keep memberships in any other tenants.
- **Transfer ownership** — promotes the member to owner; you become a regular member.

The page also shows pending invitations with **Resend** (rotates the token, resets the 14-day expiry) and **Revoke** (the link no longer works).

**Rename** updates the tenant name visible to all members and in the switcher.

## Leaving and deleting a tenant

- **Members** can leave via Settings → Team → Leave tenant at any time.
- **Owners** cannot leave. To step back, transfer ownership to an existing member first, then leave as a regular member.
- **Owners who are the sole user** of a tenant see a Delete tenant action on the team page. This permanently removes the tenant and all its data after a strong confirmation.

## I tried Distilled solo before my company adopted it

Common path: you signed up alone, played around, then your CTO invited you to the company tenant.

1. Click the invite link in your email — you'll be added to the company tenant on top of your existing personal one.
2. Use the tenant switcher to flip between them.
3. To clean up your personal tenant, switch to it, open Settings → Team, and click **Delete tenant** (only available because you're the sole user). All your personal data is removed.
