# Lessons

## Commit messages

- Do not include `Co-Authored-By` trailers in commit messages.

## Documentation

- Keep the full Makefile targets table in the root README — it's a valued
  quick reference. Trim prose for brevity, not reference tables.

## Refactoring

- Don't rename established directories/modules purely for conceptual purity
  (e.g. `middleware/` → `dependencies/`). The owner prefers keeping familiar
  names; clarify a misleading name with a docstring and a docs note instead,
  and raise the rename as a question rather than doing it.

## Logging

- Never assert a cause in a log line the response didn't state. `403` from
  GitHub had been logged as "likely plan-gated private repo"; on an enterprise
  account it was a missing permission, and the guess sent the investigation the
  wrong way. Log the upstream's own `message` field and let the reader classify.
- The same applies to inferred state: a missing `Environment` row was logged as
  "non-prod environment", which conflated "classified not production" with
  "never discovered". Distinguish the cases, or say only what you know.

## Tooling

- `poetry run <tool>` falls back to `PATH` when the project venv is empty, so a
  missing `poetry install` surfaces as a bogus source error rather than
  "command not found". A uv-installed mypy on Python 3.11 reported
  `pagination.py: Expected '('` — it cannot parse PEP 695 generics — and that
  was reported to the user as a pre-existing failure on `main`. Confirming the
  file is unchanged on `main` does not establish that: check the tool is the
  project's own (`poetry run which <tool>`, `poetry env info --path`) before
  calling any baseline failure pre-existing.

## Working with the repo

- Fetch and rebase from `main` *before* writing new design documents. A PRD and
  an RFC were written into `docs/prds/` and `docs/rfcs/` while main was
  consolidating both into `docs/proposals/`, so the work had to be redone in the
  new structure.

## React effects

- A `startedRef`/`mintedRef` "run once" guard combined with a `cancelled` flag in
  the cleanup is a deadlock under StrictMode: the first run mints and is torn
  down (setting `cancelled`), the remount hits the guard and returns, and the
  in-flight result is then discarded. The screen sits on its pending state for
  ever. Keep the guard, drop the cancellation — or the run that did the work
  must still apply its result.
- Mount components in tests the way the app mounts them. `OnboardingScreen`'s
  tests passed for months because the test provider resolved the workspace
  *after* mount, so `isOwner` started false and the effect re-ran on a
  dependency change instead of being double-invoked. The app renders it only
  once the workspace is known, which is the broken path.
- Wire a new prop through the real composition, and test it there. A
  `ProfileMenu` entry was added and unit-tested by passing the handler straight
  to `ProfileMenu`, but the app renders it via `DashboardControls`, which never
  forwarded the prop — so the menu item did not exist in the running app while
  its test passed.
