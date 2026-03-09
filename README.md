# Distilled

Full-stack app: FastAPI backend + React frontend.

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

| Target       | Description          |
|-------------|----------------------|
| `dev`        | Run both concurrently |
| `dev-server` | Server only (port 8000) |
| `dev-client` | Client only (port 5173) |
