import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GitHubInstallation(TimestampMixin, Base):
    """A GitHub App installation — a global record, not owned by any workspace.

    One GitHub account holds at most one installation of the App; workspaces
    attach to it via tenant_installations.
    """

    __tablename__ = "github_installations"
    __table_args__ = (
        UniqueConstraint("installation_id", name="uq_github_installations_installation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    installation_id: Mapped[int] = mapped_column(BigInteger)
    account_login: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(50))
    # Soft delete: set on installation.deleted, cleared on re-install.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
