# Distilled

Distilled is a self-serve engineering intelligence tool for leaders who want clarity, not clutter. Connect GitHub and it turns your pull requests and deployments into a small set of delivery metrics you can trust — how often you ship, how long change takes to reach production, and where work is quietly getting stuck. Every number is grounded in real PRs and deployments, not manual reporting.

![Distilled Screenshot](website/src/images/distilled-screenshot.png)

## Prerequisites

- Python 3.12+ with [Poetry](https://python-poetry.org/)
- Node 20+ via [nvm](https://github.com/nvm-sh/nvm) (`.nvmrc` in `client/`)
- [Docker](https://docs.docker.com/get-docker/) (for Postgres)
- Make

## Quick start

```sh
# install dependencies
cd server && poetry install && cd ..
cd client && nvm use && npm install && cd ..

# configure
cd server && cp .env.example .env && cd ..

# database
make db-up
make migrate

# run both server and client
make dev
```

- Client: http://localhost:5173
- Server: http://localhost:8000
- API docs: http://localhost:8000/docs
- DB browser: http://localhost:5050

For full setup including the GitHub App integration, see the [local setup runbook](docs/runbooks/local-setup.md).

## Structure

```
server/   # FastAPI + Poetry
client/   # React + Vite + TypeScript + Tailwind
e2e/      # Playwright browser smoke tests
docs/     # Architecture, RFCs, ADRs, runbooks
Makefile  # dev commands + database management
```

## Everyday commands

```sh
make dev          # run server + client
make test         # run all tests
make lint         # ruff + mypy + eslint + prettier
make seed-demo    # seed realistic demo data
```

Run `make help` for the full list, including database management, coverage, formatting, and browser smoke tests.

## Documentation

Everything lives in `/docs`; key starting points:

- [Architecture](docs/architecture.md)
- [Metrics](docs/metrics.md)
- [Local Setup Runbook](docs/runbooks/local-setup.md)
