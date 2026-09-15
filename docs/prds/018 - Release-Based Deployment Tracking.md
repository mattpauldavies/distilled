# Release-Based Deployment Tracking

## Summary

Let each tracked repository decide what counts as a deployment: a successful **GitHub deployment** to a production environment (today's behaviour) or a **published GitHub release**. The choice is made per repository on a new **Settings → Deployment Tracking** page reached from the profile menu. Repositories set to release tracking stop counting `deployment_status` events and start counting `release.published` events instead. Everything downstream — deployment frequency, lead time, PR attribution, the deployments list — carries on unchanged, because a deployment is still a deployment whichever webhook produced it.

---

## Problem

Distilled has exactly one definition of a deployment: a `deployment_status` webhook with `state: success` for an environment the workspace has classified as production (`docs/rfcs/001-deployment-detection.md`, `docs/rfcs/024-production-environment-detection.md`). That definition assumes a team uses GitHub Deployments — the Deployments API, environments, and deployment statuses.

Plenty of teams don't:

- They ship from a pipeline that never calls the Deployments API (a raw `kubectl` step, a Terraform apply, a platform like Railway or Fly that doesn't write deployment statuses back to GitHub).
- They version and ship **releases**: cutting a tag, publishing a GitHub Release, and letting a workflow or a downstream consumer pick it up. This is the norm for libraries, SDKs, mobile apps, desktop apps, and anything shipped on a versioned cadence.
- They use environments for preview/staging only, so nothing in GitHub is marked production.

For those teams, three of the four dashboard sections (deployment frequency, lead time, PR cycle time) sit permanently in `setup_required`. Distilled looks broken on first contact, and the fix we currently offer — "start using GitHub Deployments" — asks them to change how they ship in order to be measured. That is the wrong way round.

The signal these teams already emit is a published release. We should read it.

---

## Goals

1. Let a workspace owner choose, per repository, whether deployments are tracked from **deployment events** or from **releases**.
2. Make the choice from a settings page reached via the profile menu, consistent with the existing Team and Repositories settings pages.
3. Ingest `release.published` events into the same deployment record the rest of the product already reads, so every existing metric, chart and list works with no further change.
4. Make the switch immediate and non-destructive: the new source starts counting from the next matching event, and history already recorded stays where it is.
5. Stop showing `setup_required` to repositories tracking releases — a published release is production by definition, so no environment classification is required.
6. Record which source produced each deployment, for support and future reporting.

---

## Non-Goals

- **Backfilling history.** Switching to releases does not import past releases from the GitHub API. Deployment tracking has never backfilled, and release tracking starts from the next published release. (Releases are backfillable in principle — a future PRD may take it on.)
- **Counting both sources at once.** A repository counts one source or the other. A repo that both deploys and releases would double count, and "which one is real?" is a question only the team can answer.
- **Pre-releases, drafts, and release edits.** Only a published, non-draft, non-pre-release release counts. Editing or deleting a release afterwards does not change what was recorded.
- **Tag-only tracking.** Pushing a tag without publishing a release does not count. A release is a deliberate act; a tag is not.
- **Other sources.** No CI workflow runs, no merge-to-main, no third-party deployment tools. The seam this work introduces makes them cheap to add later.
- **Per-workspace defaults.** Every repository starts on deployment tracking, including newly added ones. There is no workspace-level default to inherit.
- **Changing what a "production environment" means** for repositories that stay on deployment tracking.

---

## Users

**Primary (workspace owner):** An engineering leader whose team ships by publishing releases, or whose pipeline doesn't write deployment statuses to GitHub. Today their dashboard shows "setup required" and they have no way to fix it from inside the product. They want to point Distilled at the signal their team already emits and see real numbers, in under a minute, without talking to anyone.

**Secondary (workspace member):** Sees the resulting metrics. Does not configure tracking, but needs the dashboard to be honest about what is being counted.

---

## Concepts

### Deployment source

A per-repository setting with two values:

| Source        | Counts                                                                 | Default |
| ------------- | ---------------------------------------------------------------------- | ------- |
| `deployment`  | `deployment_status` events with `state: success` on a production environment | ✅ yes  |
| `release`     | `release` events with action `published`, excluding drafts and pre-releases | —       |

The setting lives on the repository, not the workspace: a workspace commonly holds both services (which deploy) and libraries (which release), and forcing one answer across both would make half of them wrong.

### A deployment is a deployment

Whatever produced it, a recorded deployment is one row with a timestamp, a ref, and a link. Deployment frequency counts it; PR attribution windows run between consecutive ones; lead time measures merge → deployed. The source is recorded for traceability, but no metric filters on it: a repository that ran on deployment events for six months and then switched to releases has one continuous history, not two.

### Production, for releases

Deployment tracking requires a production environment because GitHub deployments target arbitrary environments and most of them are not production. Releases have no environment: publishing a release *is* the act of shipping. So release-tracked repositories need no environment classification, and must not be asked for one.

---

## Workflows

### Switching a repository to release tracking

1. Owner opens the profile menu → **Deployment Tracking**.
2. The page lists every repository the workspace tracks, each with a two-option control: **Deployments** / **Releases**.
3. Owner switches `acme/sdk` to **Releases**. The change saves immediately and is confirmed in place.
4. The next published release on `acme/sdk` is recorded as a deployment. Deployment statuses on that repository are ignored from the moment of the switch.

### Switching back

The reverse, with the same immediacy. Releases recorded while the repo was in release mode stay in the history and keep counting.

### A release is published

1. GitHub sends a `release` webhook with action `published`.
2. Distilled records a deployment for every workspace tracking that repository **in release mode**, timestamped at the release's publication time, with the tag as its ref and the release page as its link.
3. PRs merged to the default branch since the previous deployment are attributed to it, exactly as for deployment events.
4. Drafts and pre-releases are ignored.

---

## UI / Screens

### Profile menu

A third owner-only entry, **Deployment Tracking**, alongside Team Settings and Repositories.

### Settings → Deployment Tracking

- Header consistent with the existing settings pages (`Settings · Deployment Tracking`, "Back to dashboard").
- One line of explanation: what the choice means and that it takes effect from the next event.
- A row per tracked repository: full name, current source control, and — for release-tracked repos — no environment nagging.
- Deployment-tracked repositories with no production environment keep the existing guidance; this page is where switching to releases becomes the obvious fix.
- Saves on change, per repository. A failed save says so and leaves the previous value showing.

### Dashboard

- Release-tracked repositories no longer show `setup_required` for deployment frequency, lead time or PR cycle time.
- Where the dashboard explains a missing production environment, it must not do so for a release-tracked repository.

---

## GitHub App permission

Subscribing to the `release` webhook event requires the App's **Contents: read** permission — the one permission `docs/github-app.md` currently records as deliberately not requested. Adding it means every existing installation is prompted by GitHub to approve the new permission, and release events are not delivered to an installation until someone approves.

This is a genuine widening of the App's access and is the main cost of this feature. It is documented in an ADR alongside the RFC, `docs/github-app.md` is updated to state exactly what is requested and why, and the settings page tells the owner that release tracking needs the updated permission to be accepted on GitHub.

---

## Edge Cases & Behaviour

| Case                                                                | Behaviour                                                                 |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Release published while the repo is in deployment mode              | Ignored, recorded as a skipped delivery.                                  |
| Deployment succeeds while the repo is in release mode               | Ignored, recorded as a skipped delivery.                                  |
| Same repo tracked by two workspaces with different sources          | Each workspace counts its own source. Both events are delivered once and fan out independently. |
| Pre-release or draft published                                      | Ignored.                                                                  |
| Pre-release later promoted to a full release                        | Not counted in v1 (the promotion fires `release.released`, out of scope). |
| Release edited or deleted after publication                         | The recorded deployment stands.                                           |
| The same release delivered twice (webhook redelivery)               | Idempotent — one deployment.                                              |
| Release published on a repository with no production environment    | Counted. Environments are irrelevant in release mode.                     |
| Switching sources mid-window                                        | No recomputation, no deletion. The history is continuous.                 |
| Installation has not approved Contents: read                        | No release events arrive. The repo looks quiet; the settings page warns about this up front. |

---

## Acceptance Criteria

### Configuration

- A workspace owner can set each tracked repository's deployment source to `deployment` or `release` from the profile menu.
- Members cannot change it.
- New repositories default to `deployment`.
- The setting persists and is reflected on reload.

### Ingest

- A `release.published` event on a release-tracked repository records exactly one deployment per tracking workspace, timestamped at publication.
- Drafts and pre-releases record nothing.
- `deployment_status` events on a release-tracked repository record nothing.
- `release` events on a deployment-tracked repository record nothing.
- Redelivery of the same release records nothing further.
- PRs merged since the previous deployment are attributed to a release-sourced deployment.

### Metrics & dashboard

- Deployment frequency, lead time and PR cycle time return real data for a release-tracked repository with no production environment.
- Deployments recorded from releases appear in the deployments list with their tag and a link to the release.
- Existing deployment-tracked repositories behave exactly as before.

### Documentation

- `docs/github-app.md` lists the `release` event and the Contents: read permission with its justification.
- An ADR records the permission decision.
- `docs/metrics.md` states both definitions of a deployment.
