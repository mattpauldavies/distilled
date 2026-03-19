# RFC 014: Linting

## Context

The client has a basic ESLint setup (TypeScript + react-hooks + react-refresh). The server has no linting or formatting tooling. Neither side has formatting enforced. This RFC establishes a consistent, enforced linting and formatting baseline across both layers.

## Goals

- Catch common bugs and style issues at dev time and in CI
- Enforce consistent formatting so diffs stay clean
- Keep tooling minimal and fast

## Frontend (Client)

**Already in place:** ESLint flat config with `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`.

**Add Prettier** for deterministic formatting:

- `prettier` — formatter
- `eslint-config-prettier` — disables ESLint rules that conflict with Prettier

Config files:
- `.prettierrc` — opinionated defaults (single quotes, no semicolons, trailing commas)
- ESLint config extended with `prettier` at the end of the config chain

New npm scripts:
```
"format": "prettier --write ."
"format:check": "prettier --check ."
```

Update `lint` script to also check formatting:
```
"lint": "eslint . && prettier --check ."
```

## Backend (Server)

**Add Ruff** — replaces flake8, isort, pyupgrade, and provides Black-compatible formatting. Fast (Rust-based), single tool, configured in `pyproject.toml`.

**Add mypy** — static type checking. Already enforced implicitly via Pydantic + FastAPI, but not checked at CI time.

`pyproject.toml` additions:

```toml
[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
# E/F = pycodestyle/pyflakes, I = isort, UP = pyupgrade, B = bugbear

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
```

New Poetry dev dependencies:
- `ruff` (linting + formatting)
- `mypy` (type checking)

## Makefile Targets

```make
lint: lint-server lint-client

lint-server:
    cd server && poetry run ruff check . && poetry run mypy app

lint-client:
    cd client && npm run lint

format: format-server format-client

format-server:
    cd server && poetry run ruff format .

format-client:
    cd client && npm run format
```

## CI Integration

Extend `.github/workflows/deploy.yml` (or add a dedicated `lint.yml` workflow) to run `make lint` on every push and pull request.

```yaml
lint:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.12" }
    - uses: actions/setup-node@v4
      with: { node-version: "20" }
    - run: cd server && pip install poetry && poetry install && poetry run ruff check . && poetry run mypy app
    - run: cd client && npm ci && npm run lint
```

## Non-Goals

- No auto-fixing in CI (check only — developers fix locally)
- No pre-commit hooks (optional developer opt-in, not enforced)
- No additional ESLint rule sets beyond what's already configured

---

## Implementation Plan

*(Appended after RFC approval)*
