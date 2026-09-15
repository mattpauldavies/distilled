"""per-repo deployment source, event source, drop unused deployment columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-15 16:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Postgres' default name for the unnamed UniqueConstraint in 001_initial_schema.
_OLD_UNIQUE = "deployment_events_tenant_id_deployment_id_key"
_NEW_UNIQUE = "uq_deployment_events_tenant_source_deployment"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "repositories",
        sa.Column(
            "deployment_source",
            sa.String(20),
            nullable=False,
            server_default="deployment",
        ),
    )
    op.add_column(
        "deployment_events",
        sa.Column("source", sa.String(20), nullable=False, server_default="deployment"),
    )

    # Deployment ids and release ids are separate id spaces sharing one column:
    # without source in the key, a release could collide with a deployment and
    # be dropped as a duplicate.
    op.drop_constraint(_OLD_UNIQUE, "deployment_events", type_="unique")
    op.create_unique_constraint(
        _NEW_UNIQUE, "deployment_events", ["tenant_id", "source", "deployment_id"]
    )

    op.drop_column("deployment_events", "ref")
    op.drop_column("deployment_events", "commit_sha")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "deployment_events",
        sa.Column("commit_sha", sa.String(40), nullable=False, server_default=""),
    )
    op.add_column(
        "deployment_events",
        sa.Column("ref", sa.String(255), nullable=False, server_default=""),
    )

    # Release-sourced rows cannot be represented once source is gone, and they
    # would break the narrower unique constraint.
    op.execute("DELETE FROM deployment_events WHERE source = 'release'")

    op.drop_constraint(_NEW_UNIQUE, "deployment_events", type_="unique")
    op.create_unique_constraint(_OLD_UNIQUE, "deployment_events", ["tenant_id", "deployment_id"])

    op.drop_column("deployment_events", "source")
    op.drop_column("repositories", "deployment_source")
