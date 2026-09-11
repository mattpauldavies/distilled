"""github_installations become global: drop tenant_id, unique installation_id

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-10 12:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Defensive de-duplication: the old code could not create two rows for one
    # installation_id, but the old schema allowed it. Keep the oldest row,
    # repoint references, delete the rest.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, installation_id,
                   first_value(id) OVER (
                       PARTITION BY installation_id ORDER BY created_at, id
                   ) AS keep_id
            FROM github_installations
        ),
        dupes AS (
            SELECT id, keep_id FROM ranked WHERE id <> keep_id
        ),
        repoint_repos AS (
            UPDATE repositories r
            SET installation_id = d.keep_id
            FROM dupes d
            WHERE r.installation_id = d.id
            RETURNING r.id
        ),
        repoint_links AS (
            UPDATE tenant_installations ti
            SET github_installation_id = d.keep_id
            FROM dupes d
            WHERE ti.github_installation_id = d.id
              AND NOT EXISTS (
                  SELECT 1 FROM tenant_installations existing
                  WHERE existing.tenant_id = ti.tenant_id
                    AND existing.github_installation_id = d.keep_id
              )
            RETURNING ti.id
        )
        DELETE FROM github_installations gi
        USING dupes d
        WHERE gi.id = d.id
        """
    )
    # Links that couldn't be repointed (target link already existed) now dangle
    # onto deleted rows — ON DELETE CASCADE on tenant_installations removed them.

    op.drop_column("github_installations", "tenant_id")
    op.create_unique_constraint(
        "uq_github_installations_installation_id", "github_installations", ["installation_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_github_installations_installation_id", "github_installations", type_="unique"
    )
    op.add_column("github_installations", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "github_installations_tenant_id_fkey",
        "github_installations",
        "tenants",
        ["tenant_id"],
        ["id"],
    )
    # Best-effort restore: point each installation at one linked tenant.
    op.execute(
        """
        UPDATE github_installations gi
        SET tenant_id = ti.tenant_id
        FROM (
            SELECT DISTINCT ON (github_installation_id) github_installation_id, tenant_id
            FROM tenant_installations
            ORDER BY github_installation_id, created_at
        ) ti
        WHERE ti.github_installation_id = gi.id
        """
    )
