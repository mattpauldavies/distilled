# Lessons

## Commit messages

- Do not include `Co-Authored-By` trailers in commit messages.

## Refactoring

- Don't rename established directories/modules purely for conceptual purity
  (e.g. `middleware/` → `dependencies/`). The owner prefers keeping familiar
  names; clarify a misleading name with a docstring and a docs note instead,
  and raise the rename as a question rather than doing it.
