# GitHub App surface

Everything Distilled asks of GitHub, derived from the code rather than from
habit: four API calls, two webhook events we subscribe to, and two more GitHub
delivers whether we ask or not. The permission set below is the minimum that
makes all of it work — anything beyond it is access we do not use.

---

## What the server calls

All four calls live in `server/app/services/github_client.py`.

| Call                                     | Auth                    | Used by                                    | Permission required        |
| ---------------------------------------- | ----------------------- | ------------------------------------------ | -------------------------- |
| `POST /app/installations/{id}/access_tokens` | App JWT             | every installation-authenticated call      | none (app-level)           |
| `GET /app/installations/{id}`            | App JWT                 | binding an installation ahead of its webhook | none (app-level)         |
| `GET /installation/repositories`         | Installation token      | repo sync, available-repo picker           | **Metadata: read**         |
| `GET /repos/{owner}/{repo}/environments` | Installation token      | environment discovery at install/sync time | **Actions: read**          |

The app-JWT endpoints are authenticated by the App's private key, so no
installation permission applies to them. A failure there is a credentials
problem (`GITHUB_APP_ID`, private key, clock skew), not a grant problem.

**`Actions: read` is the surprise.** Listing a repository's deployment
environments is documented under Deployments, but GitHub checks the *Actions*
repository permission for it — the `Environments` permission governs
environment secrets, variables and protection rules, not the list endpoint. An
installation holding Deployments, Pull requests and Metadata but not Actions
gets `403 Resource not accessible by integration` here, on every plan.

## What the server receives

Handlers are registered with `@register_handler` and dispatched from
`POST /webhooks/github`.

| Event                       | Actions handled                                              | Delivery                       | Permission required     |
| --------------------------- | ------------------------------------------------------------ | ------------------------------ | ----------------------- |
| `pull_request`              | `opened`, `reopened`, `closed`, `converted_to_draft`, `ready_for_review` | subscribe in App settings | **Pull requests: read** |
| `deployment_status`         | `success` states only                                         | subscribe in App settings      | **Deployments: read**   |
| `installation`              | `created`, `deleted`                                          | always delivered               | none                    |
| `installation_repositories` | `added`, `removed`                                            | always delivered               | none                    |

`installation` and `installation_repositories` are sent to every GitHub App
automatically — they are not in the event list in App settings, and nothing
needs to be ticked for them to arrive. Every other event type reaches
`_dispatch_event`, finds no handler, and is recorded as `no_handler` in
`webhook_events`; subscribing to more than the two above only adds noise.

## Minimum permission set

| Permission    | Access    | Why                                                        |
| ------------- | --------- | ---------------------------------------------------------- |
| Metadata      | Read-only | Mandatory for any App; `GET /installation/repositories`    |
| Pull requests | Read-only | `pull_request` event subscription                          |
| Deployments   | Read-only | `deployment_status` event subscription                     |
| Actions       | Read-only | `GET /repos/{owner}/{repo}/environments`                   |

Deliberately **not** requested: Contents, Checks, Commit statuses, Issues,
Administration, Members, Environments. Distilled reads no source, no build
results and no organisation membership — PR and deployment metadata is the
whole diet.

Changing an App's permissions does not apply retroactively: GitHub emails the
account owner of every existing installation to accept the new permission, and
until they do, that installation's token keeps the old set.

## Diagnosing a refusal

Three log lines carry GitHub's own message, which is what distinguishes the
causes. None of them assert a cause the response didn't state.

| Log line                   | Means                                                             |
| -------------------------- | ----------------------------------------------------------------- |
| `environments_forbidden`   | `GET …/environments` returned 403. Read `github_message`: `Resource not accessible by integration` is a missing **Actions: read** grant; `Upgrade to GitHub Pro…` is plan gating on a private repo of a Free personal account; a SAML/IP message is an org policy. |
| `environment_unknown`      | A deployment arrived for an environment with no row — discovery never ran or was refused. The deployment is not counted. |
| `installation_token_failed` | The App JWT itself was rejected — wrong app id, wrong private key, or clock skew. |

The failure mode is quiet by design: environment discovery degrades to "no
environments" rather than failing an install. The cost is that every
`deployment_status` for that repo is then dropped (`environment_unknown`), so
its deployment frequency and lead time stay empty while everything else looks
healthy. A repo with PRs but no deployments is the symptom to look for.

## Related

- Setup walkthrough: [local setup runbook](runbooks/local-setup.md)
- Webhook handling and the delivery audit: [server README](../server/README.md#webhook-events)
- Redelivering a missed event: [webhook redelivery runbook](runbooks/webhook-redelivery.md)
