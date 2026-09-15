# Proposals

One document per capability. Each proposal states what we set out to build, the design that
survived, the decisions and their trade-offs, and what is still open.

These replaced three folders — `prds/`, `rfcs/`, and `adrs/` — that split a single feature's
story across up to four files and, in places, described superseded designs as though they
were current.

| #                                                | Area                                                                   | Status  |
| ------------------------------------------------ | ---------------------------------------------------------------------- | ------- |
| [001](001-deployment-ingest.md)                  | GitHub webhooks, deployment detection, PR ingest, attribution           | Shipped |
| [002](002-metrics-engine.md)                     | Metric computation, aggregate tables, scheduled recompute, data quality | Shipped |
| [003](003-dashboard.md)                          | Dashboard API and UI                                                    | Shipped |
| [004](004-accounts-and-workspaces.md)            | Identity, workspaces, membership, invitations, GitHub installations     | Shipped |
| [005](005-security.md)                           | Security posture, audits, open backlog                                  | Shipped |
| [006](006-observability.md)                      | Logging, error reporting, product analytics                             | Shipped |
| [007](007-build-and-deployment.md)               | Containerised builds, migrations, website URL contract                  | Shipped |
| [008](008-engineering-practice.md)               | Testing, linting, demo data, layering conventions                       | Shipped |
| [009](009-reliability-metrics.md)                | Change failure rate and MTTR via incident.io                            | **Proposed** |

## Where things live

Proposals record **intent and decisions** — why the system is the way it is. They are not the
reference documentation.

- [architecture.md](../architecture.md) — how the system works today
- [metrics.md](../metrics.md) — what each metric means
- [github-app.md](../github-app.md) — the GitHub App surface and permissions
- [getting-started.md](../getting-started.md) — using the product
- [analytics.md](../analytics.md) — what we collect
- [runbooks/](../runbooks/) — operational procedures
- [lessons.md](../lessons.md) — patterns learnt from corrections

When a proposal and the reference docs disagree, the reference docs are right and the
proposal needs a History entry.

## Writing one

For anything beyond a small bug fix, start a proposal and follow the workflow in
[CLAUDE.md](../../CLAUDE.md): describe the problem, get the technical design agreed, then
implement.

Keep them short. A proposal is worth reading six months later only if it says what was
decided and why — not how every file was edited. Implementation belongs in the commits.

Sections that have earned their place:

- **Summary** — what this is, in a few sentences
- **Goals / Non-goals** — especially non-goals; they age best
- **Design** — the shape that survived, not every shape considered
- **Decisions** — each with its reasoning and its cost
- **Accepted consequences** — what we knowingly gave up
- **Open items / Deferred** — what a future reader should not assume is finished
- **History** — how the design changed, so superseded ideas are dated rather than deleted

When work lands, update the relevant proposal rather than writing a new one. A new proposal
is for a new capability.
