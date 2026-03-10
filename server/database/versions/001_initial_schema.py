"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "github_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "installation_id"),
    )

    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["installation_id"], ["github_installations.id"]),
        sa.UniqueConstraint("tenant_id", "github_id"),
    )

    op.create_table(
        "environments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_production", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["repo_id"], ["repositories.id"]),
        sa.UniqueConstraint("tenant_id", "repo_id", "name"),
    )

    op.create_table(
        "deployment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("environment_name", sa.String(255), nullable=False),
        sa.Column("deployment_id", sa.BigInteger(), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("ref", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("deployed_at", sa.DateTime(), nullable=False),
        sa.Column("html_url", sa.String(2048), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["repo_id"], ["repositories.id"]),
        sa.UniqueConstraint("tenant_id", "deployment_id"),
    )

    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("base_ref", sa.String(255), nullable=False),
        sa.Column("merged_at", sa.DateTime(), nullable=False),
        sa.Column("merge_commit_sha", sa.String(40), nullable=False),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("author_login", sa.String(255), nullable=False),
        sa.Column("html_url", sa.String(2048), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["repo_id"], ["repositories.id"]),
        sa.UniqueConstraint("tenant_id", "repo_id", "number"),
    )

    op.create_table(
        "deployment_attributions",
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("pr_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("deployment_id", "pr_id"),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployment_events.id"]),
        sa.ForeignKeyConstraint(["pr_id"], ["pull_requests.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    # Seed dev tenant
    op.execute(
        "INSERT INTO tenants (id, name) VALUES "
        "('00000000-0000-0000-0000-000000000001', 'dev') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("deployment_attributions")
    op.drop_table("pull_requests")
    op.drop_table("deployment_events")
    op.drop_table("environments")
    op.drop_table("repositories")
    op.drop_table("github_installations")
    op.drop_table("tenants")
