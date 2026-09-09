# ADR 005 — Containerised Server Build

**Date:** 2026-09-09
**Status:** Accepted

## Context

The server was deployed from source and left the platform to infer a Python
toolchain. On Railway that means the Railpack builder, which installs
interpreters via `mise`. `mise` releases from 2026 onwards verify a GitHub build
attestation for every python-build-standalone download, and older
python-build-standalone releases — including the `3.12.4` pinned in
`server/.python-version` — predate attestations, so the build failed with:

```
mise ERROR Failed to install core:python@3.12.4: No GitHub artifact
```

The workarounds available inside that model (setting
`MISE_PYTHON_GITHUB_ATTESTATIONS=false`, or chasing a patch release whose
artefacts happen to be signed) leave the build dependent on a toolchain we
neither pin nor test, and on a policy the builder can change again.

The client and website were already containerised (a static build served by
Caddy), so the platform-agnostic build path was established.

## Decision

**The server ships as a container.** `server/Dockerfile` is a two-stage build:
Poetry installs the locked production dependencies into an in-project virtualenv
on `python:3.12.14-slim-bookworm`, and the runtime stage copies that virtualenv
onto the same base image, drops to a non-root user, and runs
`uvicorn app.main:app` on `$PORT`.

The interpreter patch version is pinned in both the `Dockerfile` and
`server/.python-version`, which are bumped together.

Migrations are not run by the image's entrypoint; they stay an explicit
release-phase command (`alembic upgrade head`), so a schema change is a
deliberate step rather than a side effect of a container starting.

## Consequences

- The build no longer depends on the host platform's language detection, its
  interpreter provisioning, or that provisioner's verification policy.
- The same image runs locally, in a preview environment and in production.
- Interpreter and dependency upgrades are explicit commits, reviewable in the
  diff.
- The image must be rebuilt to pick up a Python patch release; there is no
  automatic drift.
