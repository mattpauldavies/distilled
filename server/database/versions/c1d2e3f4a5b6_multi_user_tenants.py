"""multi user tenants

Revision ID: c1d2e3f4a5b6
Revises: f1e2d3c4b5a6
Create Date: 2026-05-05 17:30:00.000000

Adds tenant_users (membership join), invitations, last_active_tenant_id,
rename_prompt_dismissed. Backfills owner memberships from users.tenant_id,
drops users.tenant_id, recasts tenant FKs as ON DELETE CASCADE.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "f1e2d3c4b5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables whose tenant_id FK becomes ON DELETE CASCADE so a single
# `DELETE FROM tenants WHERE id = ...` removes everything.
_TENANT_CASCADE_TABLES: tuple[str, ...] = (
    "github_installations",
    "repositories",
    "environments",
    "deployment_events",
    "pull_requests",
    "deployment_attributions",
    "deployment_daily_metrics",
    "lead_time_weekly_metrics",
    "pr_cycle_time_weekly_metrics",
    "pr_throughput_weekly_metrics",
    "metrics_refresh_log",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "tenant_users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_users_tenant_user"),
        sa.CheckConstraint("role IN ('owner','member')", name="ck_tenant_users_role"),
    )
    op.create_index(
        "uq_tenant_users_one_owner",
        "tenant_users",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )

    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.dialects.postgresql.CITEXT(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index(
        "uq_invitations_open_tenant_email",
        "invitations",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("redeemed_at IS NULL AND revoked_at IS NULL"),
    )

    op.add_column(
        "users",
        sa.Column("last_active_tenant_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "users_last_active_tenant_id_fkey",
        "users",
        "tenants",
        ["last_active_tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "tenants",
        sa.Column(
            "rename_prompt_dismissed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Backfill: every existing user becomes the owner of their tenant, and that
    # tenant is their last-active tenant.
    op.execute(
        """
        INSERT INTO tenant_users (id, tenant_id, user_id, role, created_at, updated_at)
        SELECT gen_random_uuid(), tenant_id, id, 'owner', now(), now()
          FROM users
        """
    )
    op.execute("UPDATE users SET last_active_tenant_id = tenant_id")

    # Drop users.tenant_id; membership is now the source of truth.
    op.drop_constraint("users_tenant_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "tenant_id")

    # Recast tenant FKs as ON DELETE CASCADE so deleting a tenant removes all
    # dependent rows in a single statement.
    for table in _TENANT_CASCADE_TABLES:
        op.drop_constraint(f"{table}_tenant_id_fkey", table, type_="foreignkey")
        op.create_foreign_key(
            f"{table}_tenant_id_fkey",
            table,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table in _TENANT_CASCADE_TABLES:
        op.drop_constraint(f"{table}_tenant_id_fkey", table, type_="foreignkey")
        op.create_foreign_key(
            f"{table}_tenant_id_fkey",
            table,
            "tenants",
            ["tenant_id"],
            ["id"],
        )

    op.add_column("users", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE users u
           SET tenant_id = (
                SELECT tenant_id FROM tenant_users tu
                 WHERE tu.user_id = u.id AND tu.role = 'owner'
                 LIMIT 1
           )
        """
    )
    op.alter_column("users", "tenant_id", nullable=False)
    op.create_foreign_key("users_tenant_id_fkey", "users", "tenants", ["tenant_id"], ["id"])

    op.drop_column("tenants", "rename_prompt_dismissed")

    op.drop_constraint("users_last_active_tenant_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "last_active_tenant_id")

    op.drop_index("uq_invitations_open_tenant_email", table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("uq_tenant_users_one_owner", table_name="tenant_users")
    op.drop_table("tenant_users")
