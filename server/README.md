# Server

FastAPI backend for deployment detection and DORA metrics. Ingests GitHub webhooks, detects production deployments, and attributes PRs to deployments.

## Setup

```sh
cp .env.example .env  # edit as needed
poetry install
make db-up            # start Postgres
make migrate          # apply migrations
```

## Run

```sh
poetry run uvicorn app.main:app --reload --port 8000
```

## API docs

http://localhost:8000/docs (Swagger UI) or http://localhost:8000/redoc

## Structure

```
app/
  main.py          # App factory, lifespan, router registration
  config.py        # Settings via pydantic-settings (.env)
  db.py            # Async SQLAlchemy engine + session factory
  models/          # ORM models (database tables)
  schemas/         # Pydantic request/response shapes (API contract)
  routes/          # FastAPI routers (HTTP layer)
  services/        # Business logic (webhook handling, GitHub API, attribution)
  middleware/      # Request-scoped context (tenant resolution)
database/          # Alembic migrations
```
