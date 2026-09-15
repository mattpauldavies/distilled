---
name: "distilled-dev-commands"
description: "The canonical local commands for this repo — tests, lint, migrations, and the Postgres container. Use before running any server, client, website, or database command locally, and whenever a shell invocation fails on a path, a Node version, or a database role."
---
# Distilled local commands

Run everything through the Makefile from the repo root. The targets already
carry the right working directory, Node version, and Poetry environment; a
hand-rolled `cd ... && ...` re-derives them and gets them wrong.

**The Bash tool's working directory persists between calls.** A second
`cd server && ...` from inside `server/` fails with
`no such file or directory: server`. Use absolute paths, or `make` from the
repo root, rather than assuming where the previous call left you.

## Tests and lint

| Task | Command (from repo root) |
| --- | --- |
| All tests | `make test` |
| Server tests | `make test-server` |
| Client tests | `make test-client` |
| Website routing tests | `make website-test` |
| All lint + format checks | `make lint` |
| Server lint only | `make lint-server` |

`make lint` includes a Prettier format check on the client. Run it **before**
committing, not after — a formatting-only failure at the end of a long change
costs a whole extra fix-and-rerun cycle.

`make test-client` sources `~/.nvm/nvm.sh` internally. In a worktree-isolated
session that redirect is refused; call `npm test` directly from `client/`
instead, which uses the already-active Node.

## Database

Postgres runs in the `distilled-postgres-1` container. The role and database
are both `distilled` — not `postgres`:

```bash
docker exec distilled-postgres-1 psql -U distilled -d distilled -tAc "SELECT ..."
```

`docker compose up -d postgres pgweb` (or `make db-up`) starts it; `make migrate`
applies migrations. The connection string lives in `server/.env`; read it there
rather than guessing credentials.

## Before declaring a change done

Run `make test` and `make lint` from the repo root in one pass. A baseline
failure that predates your change (check it on `main` before assuming it is
yours) should be named to the user, not silently re-run.
