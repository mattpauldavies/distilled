# Getting Started

A short walkthrough of workspaces, repositories, and team flows. For solo onboarding, signing in is enough — Distilled provisions a workspace called **My Workspace** and walks you through connecting GitHub.

## First sign-in → connecting GitHub

1. Sign in with GitHub. Distilled creates a workspace named **My Workspace** and you become its **owner**.
2. The onboarding screen offers **Install GitHub App**. The link is minted for your workspace — completing the install on GitHub binds the installation (and every repository you granted) to it.
3. Repos appear within a few seconds of completing the installation, and the dashboard takes over.

You can rename the workspace at any time from **Settings → Team**.

## Workspaces

A workspace is Distilled's unit of data and membership: its own repositories, members, and metrics. A workspace is **not** a GitHub organisation — one workspace can track repositories from several orgs and personal accounts, and two users can track the same repository in their own private workspaces.

- **Create** more workspaces from the profile menu (top right) → **Create workspace**. You become the new workspace's owner; it starts empty, ready for its own GitHub connections.
- **Switch** between workspaces from the same menu. The dashboard reloads with the chosen workspace's data. Two browser tabs can hold two different active workspaces; the active workspace is sent as the `X-Workspace-Id` header on every request.

## Managing repositories (owner)

**Settings → Repositories** (profile menu) shows what the active workspace tracks:

- **Add repositories** — pick from the repositories granted to a connected installation. Already-tracked repos are shown as added.
- **Remove** — the repo disappears from this workspace's dashboard; historical data is retained but hidden, and the repo stays removed even if GitHub-side syncs re-deliver it. Add it back any time.
- **Connect GitHub** — installs the App on another org or personal account (or updates an existing installation's repo grants) and links it to this workspace.
- **Unlink** — detaches an installation from this workspace, removing its repos here. Other workspaces using the same installation are unaffected.

To move a repository between workspaces: remove it from one, then add it in the other (connect the installation there first if needed). History stays with the workspace that recorded it; the destination starts accumulating from the move.

## Adding your first teammate

1. Open **Settings → Team** from the profile menu.
2. Click **Invite member**. The first time you do this on a workspace still carrying its default name, a one-time **Name your workspace** prompt appears — change it to `Acme Engineering` or similar so teammates recognise it. You can skip the rename; the prompt won't reappear.
3. Enter your teammate's email address and **Send invite**. They'll receive a link within 30 seconds.
4. Once they click the link and sign in with GitHub, they land on the same dashboard as you.

The owner role grants access to Settings (Team and Repositories). Members see the dashboard only.

## Joining a team (invitee experience)

When you receive an invitation email and click the link:

- If you don't have a Distilled account yet, the page sends you to GitHub sign-in. After authenticating, you're automatically added to the inviting workspace — no second step.
- If you already have a Distilled account, the page redeems the invite against your current sign-in, again with no extra confirm step. The newly joined workspace becomes your active workspace; switch back via the profile menu.

The email on your GitHub account does **not** need to match the address the invite was sent to. The link itself is the credential.

If you sign in normally (without clicking the link) and your verified GitHub emails include the invited address, a banner appears at the top of the dashboard offering to accept or decline.

## Managing your team (owner)

**Settings → Team** offers, per member:

- **Remove** — revokes the member's access on their next interaction. They keep memberships in any other workspaces.
- **Transfer ownership** — promotes the member to owner; you become a regular member.

The page also shows pending invitations with **Resend** (rotates the token, resets the 14-day expiry) and **Revoke** (the link no longer works).

**Rename** updates the workspace name visible to all members and in the switcher.

## Leaving and deleting a workspace

- **Members** can leave via Settings → Team at any time.
- **Owners** cannot leave. To step back, transfer ownership to an existing member first, then leave as a regular member.
- **Owners who are the sole user** of a workspace see a Delete workspace action on the team page. This permanently removes the workspace and all its data after a strong confirmation.

## I tried Distilled solo before my company adopted it

Common path: you signed up alone, played around, then your CTO invited you to the company workspace.

1. Click the invite link in your email — you'll be added to the company workspace on top of your existing personal one.
2. Use the workspace switcher in the profile menu to flip between them.
3. To clean up your personal workspace, switch to it, open Settings → Team, and click **Delete workspace** (only available because you're the sole user). All your personal data is removed.
