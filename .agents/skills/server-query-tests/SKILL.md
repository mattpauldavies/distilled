---
name: "server-query-tests"
description: "How to test SQLAlchemy service code in /server so mocked sessions don't hide real query failures. Use when writing or changing any server service, route, or test that executes a select and consumes it with scalar_one, scalar_one_or_none, or scalars().one()."
---
# Testing server queries

Server service tests mock the session (`mock_session` in `tests/conftest.py`,
driven by `AsyncMock(side_effect=[mock_result(...), ...])`). That is the repo
convention and it stays — but it has one blind spot worth naming: a mocked
result returns exactly the rows the test handed it, so a query that can return
a *different number* of rows in production always passes.

## The rule

`scalar_one()` and `scalar_one_or_none()` raise `MultipleResultsFound` on two
or more rows. Before using either, answer: **can this query ever match more
than one row?**

- If a unique constraint or primary key guarantees at most one — fine, and say
  so in a comment naming the constraint.
- If uniqueness is only *expected* (soft-deleted rows, concurrent inserts,
  rows superseded by an UPDATE that a concurrent transaction cannot yet see),
  it is not guaranteed. Order explicitly and take one:

  ```python
  result = await session.execute(
      select(Model).where(...).order_by(Model.created_at.desc(), Model.id.desc()).limit(1)
  )
  row = result.scalar_one_or_none()
  ```

  and handle every matching row when the operation consumes them.

## The test that must exist

Any query in the "expected, not guaranteed" category needs a test that feeds
**two rows** through the mocked result and asserts the code picks the right one
without raising. Without it the mock proves nothing about the case that breaks.

Concurrency is the usual source: React StrictMode double-fires effects in dev,
so two identical POSTs can race, and neither transaction's supersede-UPDATE
sees the other's uncommitted insert. Both rows stay open. This is how the
installation webhook failed in production with `MultipleResultsFound` despite a
green suite.

## Webhook handlers specifically

A raised exception in a webhook handler rolls back the whole dispatch — nothing
from that delivery is persisted. Handlers must fail closed on untrusted data,
never on a row count the payload can influence.
