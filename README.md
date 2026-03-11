![Distilled Logo](logo-small.png)

# Distilled

Distilled is a lightweight, self-serve engineering intelligence product built for leaders who need clarity, not clutter. It turns the messy stream of day-to-day software delivery into a small set of signals that actually matter. Instead of drowning you in every metric under the sun, Distilled focuses on the measures that reflect real organisational health and presents them in a way that’s immediately understandable and easy to trust.

Distilled is designed to be effortless to adopt. Connect GitHub, and it automatically translates your production delivery into clear, auditable insights with every chart grounded in real pull requests and deployments, not manual reporting or questionable guesswork. Optionally, Distilled can expand from delivery into reliability through incident-backed integrations, creating a single, credible view of how quickly your teams ship, how long change takes to reach customers, and where friction or instability is quietly accumulating.

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
cd server && cp .env.example .env && cd ..  # edit with your GitHub App credentials

# database
make db-up        # start Postgres via Docker
make migrate      # apply migrations

# run both
make dev
```

- Client: http://localhost:5173
- Server: http://localhost:8000
- API docs: http://localhost:8000/docs

For full setup including GitHub App integration, see the [local testing runbook](docs/runbooks/local-testing.md).

## Structure

```
server/   # FastAPI + Poetry
client/   # React + Vite + TypeScript + Tailwind
docs/     # Architecture, RFCs, runbooks
Makefile  # dev commands + database management
```

## Makefile targets

| Target          | Description                                |
| --------------- | ------------------------------------------ |
| `dev`           | Run server + client concurrently           |
| `dev-server`    | Server only (port 8000)                    |
| `dev-client`    | Client only (port 5173)                    |
| `db-up`         | Start Postgres                             |
| `db-down`       | Stop Postgres                              |
| `db-reset`      | Drop volume + restart Postgres             |
| `migrate`       | Run Alembic migrations                     |
| `makemigration` | Create new migration (`MSG="description"`) |
| `test`          | Run all server tests                       |
| `test-coverage` | Run tests with coverage report             |

## Documentation

Find all documentation in `/docs` key highlights are:

- [Architecture](docs/architecture.md)
- [Local Testing Runbook](docs/runbooks/local-testing.md) — full setup guide including GitHub integration
- [RFC 001: Deployment Detection](docs/rfcs/001-deployment-detection.md) — technical spec for the deployment detection system
- [RFC 005: Metrics Aggregation Engine](docs/rfcs/005-metrics-aggregation-engine.md) — scheduled per-repo metric recompute
