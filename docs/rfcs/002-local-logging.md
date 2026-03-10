# RFC 002: Local Logging

Design spec for [PRD 002 - Local Logging](../prds/002%20-%20Local%20Logging.md).

## Approach

Stdlib logging with centralized config. No new dependencies. Works with existing `logging.getLogger(__name__)` calls across the codebase.

## Design

### Config change

Add `environment: str = "production"` to `Settings` in `config.py`. Add `ENVIRONMENT=development` to `.env` and `.env.example`.

Defaulting to `production` means deployed environments are safe without explicit config.

### Logging setup

New file: `server/app/logging.py`

```python
configure_logging(settings: Settings) -> None
```

Called once during app lifespan in `main.py`.

**Behaviour:**

- Always: configure root logger with console handler, format `{timestamp} {level} {module}: {message}`
- When `environment == "development"`: add a `FileHandler` writing to `server/logs/dev.log`
- File handler uses `mode="w"` (truncate on start)
- Both handlers use the same formatter
- Log level: `INFO`

### Log file location

`server/logs/dev.log` — add `logs/` to `.gitignore`.

### Log content

All application logs (info, warn, error) via stdlib logging. Request/response metadata captured by existing log statements in routes and services (e.g. webhook events, deployment processing).

No middleware-level request logging added — out of scope per PRD non-goals.

### Production behaviour

When `ENVIRONMENT != "development"` (default): no file handler added. Console logging only (stdout), matching current behaviour exactly.

## Files changed

| File                               | Change                                 |
| ---------------------------------- | -------------------------------------- |
| `server/app/config.py`             | Add `environment` field                |
| `server/app/logging.py`            | New — `configure_logging()`            |
| `server/app/main.py`               | Call `configure_logging()` in lifespan |
| `server/.env`                      | Add `ENVIRONMENT=development`          |
| `server/.env.example`              | Add `ENVIRONMENT=development`          |
| `.gitignore`                       | Add `logs/`                            |
| `docs/prds/002 - Local Logging.md` | Updated env var reference              |

## Not included

- Log rotation (PRD non-goal)
- Structured JSON output (plain text sufficient)
- New logging dependency (stdlib is adequate)
- Request/response middleware logging (PRD non-goal)

## Implementation Plan

### Task 1: Config + env files

1. Add `environment: str = "production"` to `Settings` in `config.py`
2. Add `ENVIRONMENT=development` to `server/.env` and `server/.env.example`

### Task 2: Tests for configure_logging

1. Create `server/tests/__init__.py` and `server/tests/test_logging.py`
2. Test: file handler added in dev, not in prod
3. Test: log file created and written to in dev
4. Test: truncation on restart
5. Test: console handler always present
6. Run tests — expect failure (module doesn't exist yet)

### Task 3: Implement configure_logging

1. Create `server/app/logging.py` with `configure_logging(settings, log_dir)`
2. Run tests — expect all pass

### Task 4: Wire into app + gitignore

1. Call `configure_logging(settings)` in `main.py` lifespan
2. Add `logs/` to `.gitignore`

### Task 5: Documentation

1. Update `server/README.md` with logging section
2. Add review section to this RFC

## Review

Implementation complete. Matches design: stdlib logging, `configure_logging()` in `app/logging.py`, called at lifespan start, file handler only in development mode. 8 tests covering dev, prod, and console handler behaviour. No new dependencies added.
