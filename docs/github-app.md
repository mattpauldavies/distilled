# GitHub App surface

Everything Distilled asks of GitHub: the four API calls and two webhook events we subscribe to.
The permission set below is the minimum that makes all of it work; anything beyond it is access we do not use.

The user-facing version of this page is
[website/src/docs/github-app.njk](../website/src/docs/github-app.njk), served at
`/docs/github-app`. A permission or event added here has to be added there too.

---

## What the server calls via the API

All four calls live in `server/app/services/github_client.py`.

| Call                                     | Auth                    | Used by                                    | Permission required        |
| ---------------------------------------- | ----------------------- | ------------------------------------------ | -------------------------- |
| `POST /app/installations/{id}/access_tokens` | App JWT             | every installation-authenticated call      | none (app-level)           |
| `GET /app/installations/{id}`            | App JWT                 | binding an installation ahead of its webhook | none (app-level)         |
| `GET /installation/repositories`         | Installation token      | repo sync, available-repo picker           | **Metadata: read**         |
| `GET /repos/{owner}/{repo}/environments` | Installation token      | environment discovery at install/sync time | **Actions: read**          |

## What the server receives via webhook events

| Event                       | Actions handled                                              | Delivery                       | Permission required     |
| --------------------------- | ------------------------------------------------------------ | ------------------------------ | ----------------------- |
| `pull_request`              | `opened`, `reopened`, `closed`, `converted_to_draft`, `ready_for_review` | subscribe in App settings | **Pull requests: read** |
| `deployment_status`         | `success` states only                                         | subscribe in App settings      | **Deployments: read**   |
| `release`                   | `published`, excluding drafts and pre-releases                | subscribe in App settings      | **Contents: read**      |
| `installation`              | `created`, `deleted`                                          | always delivered               | none                    |
| `installation_repositories` | `added`, `removed`                                            | always delivered               | none                    |

## Minimum permission set

| Permission    | Access    | Why                                                        |
| ------------- | --------- | ---------------------------------------------------------- |
| Metadata      | Read-only | Mandatory for any App; `GET /installation/repositories`    |
| Pull requests | Read-only | `pull_request` event subscription                          |
| Deployments   | Read-only | `deployment_status` event subscription                     |
| Actions       | Read-only | `GET /repos/{owner}/{repo}/environments`                   |
| Contents      | Read-only | `release` event subscription                               |

Contents is the only permission GitHub offers for release events: the gate is on
**event delivery**, not on reading anything, and there is no narrower scope. Distilled
makes no Contents API call. An installation must accept the permission before its release
events are delivered — until it does, a repository set to release tracking records nothing.

Deliberately **not** requested: Checks, Commit statuses, Issues, Administration,
Members, Environments. Distilled does not modify source code, cannot write to a
repository, and never stores user code.

