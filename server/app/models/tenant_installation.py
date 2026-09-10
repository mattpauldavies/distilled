import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TenantInstallation(TimestampMixin, Base):
    """Links a workspace (tenant) to a global GitHub App installation.

    Installations are shared resources — one GitHub account holds at most one
    installation of the App, so several workspaces may attach to the same one.
    """

    __tablename__ = "tenant_installations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "github_installation_id", name="uq_tenant_installations_tenant_installation"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    github_installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_installations.id", ondelete="CASCADE"), nullable=False
    )
