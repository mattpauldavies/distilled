# Server

FastAPI backend with in-memory item store.

## Setup

```sh
poetry install
```

## Run

```sh
poetry run uvicorn app.main:app --reload --port 8000
```

## API docs

FastAPI auto-generates interactive API documentation via OpenAPI:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Raw OpenAPI spec (JSON)**: http://localhost:8000/openapi.json

## Endpoints

| Method | Path              | Description    |
|--------|-------------------|---------------|
| GET    | `/api/health`     | Health check   |
| GET    | `/api/items`      | List items     |
| GET    | `/api/items/{id}` | Get item by ID |
| POST   | `/api/items`      | Create item    |

### Create item body

```json
{ "name": "string", "description": "string" }
```

## Structure

```
app/
  main.py             # App factory, mounts routers
  config.py           # Settings via pydantic-settings
  routes/
    health.py         # GET /health
    items.py          # CRUD routes
  services/
    item_service.py   # In-memory store
  domain/
    item.py           # Item entity
```
