# Distilled

Distilled is a lightweight, self-serve engineering intelligence product built for leaders who need clarity, not clutter. It turns the messy stream of day-to-day software delivery into a small set of signals that actually matter. Instead of drowning you in every metric under the sun, Distilled focuses on the measures that reflect real organisational health and presents them in a way that’s immediately understandable and easy to trust.

Distilled is designed to be effortless to adopt. Connect GitHub, and it automatically translates your production delivery into clear, auditable insights with every chart grounded in real pull requests and deployments, not manual reporting or questionable guesswork. Optionally, Distilled can expand from delivery into reliability through incident-backed integrations, creating a single, credible view of how quickly your teams ship, how long change takes to reach customers, and where friction or instability is quietly accumulating.

![Distilled Screenshot](website/images/distilled-screenshot.png)

## Prerequisites

- Python 3.12+ with [Poetry](https://python-poetry.org/)
- Node 20+ via [nvm](https://github.com/nvm-sh/nvm) (`.nvmrc` in `client/`)
- [Docker](https://docs.docker.com/get-docker/) (for Postgres)
- Make

## Quick start

```sh
# install deps
cd server && poetry install && cd ..
cd client && nvm use && npm install && cd ..

# configure
cd server && cp .env.example .env && cd ..
# read more at docs/runbooks/local-setup.md

# database
make db-up        # start Postgres via Docker
make migrate      # apply migrations

# run both
make dev
```

- Client: http://localhost:5173
- Server: http://localhost:8000
- API docs: http://localhost:8000/docs

For full setup including GitHub App integration, see the [local setup runbook](docs/runbooks/local-setup.md).

## Structure

```
server/   # FastAPI + Poetry
client/   # React + Vite + TypeScript + Tailwind
docs/     # Architecture, RFCs, runbooks
Makefile  # dev commands + database management
```

## Makefile targets

| Target             | Description                                |
| ------------------ | ------------------------------------------ |
| `dev`              | Run server + client concurrently           |
| `dev-server`       | Server only (port 8000)                    |
| `dev-client`       | Client only (port 5173)                    |
| `db-up`            | Start Postgres                             |
| `db-down`          | Stop Postgres                              |
| `db-reset`         | Drop volume + restart Postgres             |
| `migrate`          | Run Alembic migrations                     |
| `create-migration` | Create new migration (`MSG="description"`) |
| `test`             | Run all server + client tests              |
| `test-server`      | Server tests only                          |
| `test-client`      | Client tests only                          |
| `test-coverage`    | Server + client tests with coverage        |
| `lint`             | Lint server (ruff + mypy) + client (eslint + prettier) |
| `lint-server`      | Server lint only                           |
| `lint-client`      | Client lint only                           |
| `format`           | Auto-format server (ruff) + client (prettier) |
| `format-server`    | Server format only                         |
| `format-client`    | Client format only                         |

## Documentation

Find all documentation in `/docs` key highlights are:

- [Architecture](docs/architecture.md)
- [Local Testing Runbook](docs/runbooks/local-testing.md) — full setup guide including GitHub integration
- [RFC 001: Deployment Detection](docs/rfcs/001-deployment-detection.md) — deployment detection system
- [RFC 003: Better Python Tests](docs/rfcs/003-better-python-tests.md) — server test infrastructure + 60 tests
- [RFC 004: Client Testing](docs/rfcs/004-client-testing.md) — client test infrastructure + 27 tests
- [RFC 005: Metrics Aggregation Engine](docs/rfcs/005-metrics-aggregation-engine.md) — scheduled per-repo metric recompute
- [RFC 011: Dashboard UI](docs/rfcs/011-dashboard-ui.md) — engineering health dashboard design + implementation plan
