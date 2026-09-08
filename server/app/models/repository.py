import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("tenant_id", "github_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    installation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("github_installations.id"))
    github_id: Mapped[int] = mapped_column(BigInteger)
    full_name: Mapped[str] = mapped_column(String(255))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    # Soft delete: set when the repo is removed from the GitHub App installation,
    # cleared when it is re-added. Historical PRs/deployments/metrics keep their FK.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
