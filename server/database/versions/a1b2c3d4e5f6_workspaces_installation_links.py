"""workspaces: tenant_installations links and installation_intents

Revision ID: a1b2c3d4e5f6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-10 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tenant_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("github_installation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["github_installation_id"], ["github_installations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "github_installation_id", name="uq_tenant_installations_tenant_installation"
        ),
    )

    # Every existing installation is linked to the tenant it currently lives in.
    op.execute(
        """
        INSERT INTO tenant_installations (id, tenant_id, github_installation_id, created_at, updated_at)
        SELECT gen_random_uuid(), tenant_id, id, now(), now()
        FROM github_installations
        """
    )

    op.create_table(
        "installation_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nonce_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nonce_hash", name="uq_installation_intents_nonce_hash"),
    )

    # Transitional: installations are becoming global records. New code stops
    # writing tenant_id; the column is dropped in a follow-up migration once
    # nothing references it.
    op.alter_column("github_installations", "tenant_id", nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM github_installations WHERE tenant_id IS NULL")
    op.alter_column("github_installations", "tenant_id", nullable=False)
    op.drop_table("installation_intents")
    op.drop_table("tenant_installations")
