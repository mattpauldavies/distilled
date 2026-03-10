# Distilled

Distilled is a lightweight, self-serve engineering intelligence product built for leaders who need clarity, not clutter. It turns the messy stream of day-to-day software delivery into a small set of signals that actually matter. Instead of drowning you in every metric under the sun, Distilled focuses on the measures that reflect real organisational health and presents them in a way that’s immediately understandable and easy to trust.

Distilled is designed to be effortless to adopt. Connect GitHub, and it automatically translates your production delivery into clear, auditable insights with every chart grounded in real pull requests and deployments, not manual reporting or questionable guesswork. Optionally, Distilled can expand from delivery into reliability through incident-backed integrations, creating a single, credible view of how quickly your teams ship, how long change takes to reach customers, and where friction or instability is quietly accumulating.

## Prerequisites

- Python 3.12+ with [Poetry](https://python-poetry.org/)
- Node 20+ via [nvm](https://github.com/nvm-sh/nvm) (`.nvmrc` in `client/`)
- Make

## Quick start

```sh
# install deps
cd server && poetry install && cd ..
cd client && nvm use && npm install && cd ..

# run both
make dev
```

- Client: http://localhost:5173
- Server: http://localhost:8000
- API docs: http://localhost:8000/docs

## Structure

```
server/   # FastAPI + Poetry
client/   # React + Vite + TypeScript + Tailwind
Makefile  # dev, dev-server, dev-client
```

## Makefile targets

| Target       | Description             |
| ------------ | ----------------------- |
| `dev`        | Run both concurrently   |
| `dev-server` | Server only (port 8000) |
| `dev-client` | Client only (port 5173) |
