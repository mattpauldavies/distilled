import uuid

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ImmutableTimestampMixin, TZDatetime

SOURCE_DEPLOYMENT = "deployment"
SOURCE_RELEASE = "release"


class ProductionDeploymentEvent(ImmutableTimestampMixin, Base):
    __tablename__ = "deployment_events"
    # Deployment ids and release ids are separate id spaces sharing one column,
    # so source is part of the key.
    __table_args__ = (UniqueConstraint("tenant_id", "source", "deployment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    environment_name: Mapped[str] = mapped_column(String(255))
    deployment_id: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(20), default=SOURCE_DEPLOYMENT, server_default=SOURCE_DEPLOYMENT)
    started_at: Mapped[TZDatetime]
    completed_at: Mapped[TZDatetime]
    deployed_at: Mapped[TZDatetime]
    html_url: Mapped[str] = mapped_column(String(2048), default="")
