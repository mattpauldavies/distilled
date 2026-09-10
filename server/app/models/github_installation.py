import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GitHubInstallation(TimestampMixin, Base):
    __tablename__ = "github_installations"
    __table_args__ = (UniqueConstraint("tenant_id", "installation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Transitional: installations are global records shared across workspaces via
    # tenant_installations; this column is dropped once no code references it.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    installation_id: Mapped[int] = mapped_column(BigInteger)
    account_login: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(50))
    # Soft delete: set on installation.deleted, cleared on re-install.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
