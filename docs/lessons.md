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
