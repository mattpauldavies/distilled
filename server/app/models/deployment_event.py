import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ImmutableTimestampMixin


class ProductionDeploymentEvent(ImmutableTimestampMixin, Base):
    __tablename__ = "deployment_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "deployment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    environment_name: Mapped[str] = mapped_column(String(255))
    deployment_id: Mapped[int] = mapped_column(BigInteger)
    commit_sha: Mapped[str] = mapped_column(String(40))
    ref: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime]
    deployed_at: Mapped[datetime]
    html_url: Mapped[str] = mapped_column(String(2048), default="")
