"""backfill is_production for substring-matched environment names

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-09 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

environments = sa.table(
    "environments",
    sa.column("name", sa.String),
    sa.column("is_production", sa.Boolean),
)

# Mirrors detect_production's r"prod|live" substring match (see RFC 024).
matches_new_pattern = sa.or_(
    environments.c.name.ilike("%prod%"),
    environments.c.name.ilike("%live%"),
)


def upgrade() -> None:
    """Classify already-discovered environments under the relaxed name pattern."""
    op.execute(
        environments.update()
        .where(environments.c.is_production.is_(False), matches_new_pattern)
        .values(is_production=True)
    )


def downgrade() -> None:
    """Revert only the rows the old exact-match pattern would have rejected."""
    op.execute(
        environments.update()
        .where(
            environments.c.is_production.is_(True),
            matches_new_pattern,
            sa.not_(environments.c.name.op("~*")("^(production|prod|live)$")),
        )
        .values(is_production=False)
    )
