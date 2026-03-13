# Contributing to Distilled

Thanks for your interest in contributing to Distilled! This guide covers everything you need to get started.

## Code of Conduct

Be respectful, constructive, and inclusive. We're building something useful together — toxicity, harassment, and bad-faith behaviour have no place here.

## Getting Started

### Prerequisites

- Python 3.12+
- Node 20+ (use [nvm](https://github.com/nvm-sh/nvm))
- [Poetry](https://python-poetry.org/)
- Docker + Docker Compose
- Make

### Local Setup

```bash
# Clone the repo
git clone https://github.com/mattpauldavies/distilled.git
cd distilled

# Install backend dependencies
cd server && poetry install && cd ..

# Install frontend dependencies
cd client && nvm use && npm install && cd ..

# Configure environment
cp server/.env.example server/.env
# Edit server/.env with your GitHub App credentials

# Start Postgres and run migrations
make db-up
make migrate

# Start both server and client
make dev
```

- **Client:** http://localhost:5173
- **Server:** http://localhost:8000
- **API docs:** http://localhost:8000/docs

See [docs/runbooks/local-testing.md](docs/runbooks/local-testing.md) for detailed setup instructions.

## How to Contribute

### Reporting Bugs

Open a GitHub issue with:

- Steps to reproduce
- Expected vs actual behaviour
- Environment details (OS, browser, Python/Node versions)

### Suggesting Features

Open a GitHub issue describing the problem you're solving and why it matters. We value context over solutions — understanding the "why" helps us design the right thing.

### Submitting Code

1. **Check existing issues** — if one exists, comment that you're working on it
2. **Fork the repo** and create a feature branch from `main`
3. **Write an RFC** for non-trivial changes (see [Development Process](#development-process))
4. **Write tests** — we maintain 96% coverage and want to keep it there
5. **Open a pull request** against `main`

## Development Process

### RFCs for Non-Trivial Work

For anything beyond a small bug fix, write a short RFC in `docs/rfcs/`. This keeps design decisions documented and lets others weigh in before you invest significant effort. Include:

- Problem statement
- Proposed solution
- Alternatives considered
- Implementation plan

See existing RFCs in `docs/rfcs/` for examples.

### Branch Naming

Use descriptive branch names:

- `feat/deployment-frequency-chart`
- `fix/webhook-signature-validation`
- `docs/contributing-guide`

### Commit Messages

Keep them short and lowercase. Focus on what changed, not how.

```
add pr-ageing endpoint
fix webhook signature check for empty payloads
update docs for live metrics endpoints
```

## Running Tests

```bash
make test              # Run all tests
make test-coverage     # Run with coverage report
```

Tests live in `server/tests/` and use pytest with async support. The test suite uses mocked database sessions via FastAPI dependency overrides — see `server/tests/conftest.py` for fixtures.

### Writing Tests

- Every new endpoint or service method needs tests
- Use the existing fixtures in `conftest.py` (tenant, repo, environment, etc.)
- Tests are async by default (`asyncio_mode = "auto"`)
- `github_client.py` is excluded from coverage (external API)

## Code Style

### Backend (Python)

- Follow existing patterns in the codebase
- Use type hints
- Keep services thin — business logic in service layer, HTTP concerns in routes
- Pydantic schemas for all request/response shapes

### Frontend (TypeScript/React)

- Run `npm run lint` before committing
- Use TypeScript strictly — no `any` unless absolutely necessary
- Tailwind CSS for styling
- shadcn/ui for UI components

## Project Structure

```
server/           # FastAPI backend
  app/
    models/       # SQLAlchemy ORM models
    schemas/      # Pydantic request/response schemas
    routes/       # HTTP endpoints
    services/     # Business logic
    middleware/    # Request-scoped context (tenant, repo)
  database/       # Alembic migrations
  tests/          # pytest suite

client/           # React frontend
  src/
    components/   # UI components
    lib/          # Utilities

docs/
  rfcs/           # Design documents
  runbooks/       # Operational guides
```

## Database Changes

If your change requires a schema migration:

```bash
make create-migration MSG="add widget table"
make migrate
```

Review the generated migration in `server/database/versions/` before committing. Alembic auto-generation is helpful but not infallible — verify the SQL does what you expect.

## Pull Request Guidelines

- **Keep PRs focused** — one logical change per PR
- **Write a clear description** — what changed and why
- **Include test results** — confirm `make test` passes
- **Update docs** — if your change affects APIs, setup, or architecture, update the relevant docs in `/docs`, `/README.md`, `/server/README.md`, or `/client/README.md`
- **Link the issue** — reference the GitHub issue your PR addresses

## License

By contributing, you agree that your contributions will be licensed under the [GNU Affero General Public License v3](LICENSE.txt). This means any modifications to Distilled must also be open-sourced under AGPL-3.0, including when running as a network service.
