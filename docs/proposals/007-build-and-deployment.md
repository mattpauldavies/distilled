# Build and Deployment

**Status:** Shipped
**Consolidates:** ADR 005 (containerised server build), ADR 006 (website URL canonicalisation)

## Summary

All three surfaces — server, client, and marketing website — ship as containers. The
platform runs an image we built rather than inferring a build from the source, and the same
image runs locally, in preview, and in production.

## Containerised builds

`server/Dockerfile` is a two-stage build: Poetry installs the locked production dependencies
into an in-project virtualenv on `python:3.12.x-slim-bookworm`, and the runtime stage copies
that virtualenv onto the same base image, drops to a non-root user, and runs
`uvicorn app.main:app` on `$PORT`. The interpreter patch version is pinned in both the
Dockerfile and `server/.python-version`, bumped together.

The client and website are static builds served by Caddy.

### Why containers

The server was previously deployed from source, leaving the platform to infer a Python
toolchain. On Railway that means the Railpack builder, which installs interpreters via
`mise`. From 2026 `mise` verifies a GitHub build attestation for every
python-build-standalone download, and older releases — including the pinned `3.12.4` —
predate attestations, so the build failed outright:

```
mise ERROR Failed to install core:python@3.12.4: No GitHub artifact
```

The workarounds available inside that model — disabling attestation checks, or chasing a
patch release whose artefacts happen to be signed — leave the build dependent on a toolchain
we neither pin nor test, and on a policy the builder can change again. The client and website
were already containerised, so the platform-agnostic path was established.

The cost is explicit: the image must be rebuilt to pick up a Python patch release. There is
no automatic drift, which is the point — interpreter and dependency upgrades become commits
that show up in a diff.

## Migrations

Migrations are **not** run by the image entrypoint. They stay an explicit release-phase
command (`alembic upgrade head`), so a schema change is a deliberate step rather than a side
effect of a container starting.

## Website URL contract

Extensionless URLs are canonical, and the serving layer enforces it. `website/Caddyfile`:

- resolves a canonical URL to the flat file the build emits, via `try_files {path} {path}.html`;
- permanently redirects the `.html` form to it, preserving the query string so campaign
  parameters survive the hop;
- redirects `/index.html` and `/index` to `/`.

This exists because moving off Cloudflare Pages silently changed the contract. Pages served
`_site/terms.html` at `/terms` and redirected `/terms.html` to it; Caddy's `file_server`
matches paths against files on disk exactly, so every extensionless URL began to 404 —
indexed search results, bookmarks, and the site's own footer links, which are written as
`/terms.html` but had been rewritten to `/terms` inside any browser that visited while the
site was on Pages. Browsers cache 301s indefinitely.

Internal links point at the canonical form directly, so a click never spends a redirect.
Eleventy still emits flat `terms.html` files rather than `terms/index.html` directories: the
mapping belongs in the server that already has to redirect the legacy form, not in the build
output.

`website/test/routing.test.mjs` boots the real Caddyfile over a real build and asserts the
whole contract — canonical URLs, redirects, assets, and the 404 — with a `test-website` CI
job that installs Caddy and runs it. `SITE_ROOT` is the only concession the config makes to
being testable; the image still defaults to the `/srv` it copies the build into.

## Scheduled services

Hourly metric recompute runs as a **separate Railway cron service** pointing at the same
repo, not as a process inside the web service. Configuration lives in the Railway dashboard
rather than a `railway.toml`, because a `railway.toml` inside `server/` would be picked up by
both services and override the web service's start command. The design is in
[002 Metrics Engine](002-metrics-engine.md).

## Accepted consequences

- The image must be rebuilt for an interpreter or dependency upgrade.
- Cron service configuration is not config-as-code. If that becomes a problem, the path is a
  `railway.json` in a cron-specific subdirectory or a separate Railway project.
- Any future website host must provide extensionless resolution and the `.html` redirect, or
  reintroduce the same 404s.

## History

- **ADR 005** containerised the server after the Railpack interpreter failure.
- **ADR 006** restored the URL contract after the move off Cloudflare Pages.
