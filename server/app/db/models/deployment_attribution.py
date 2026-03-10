import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, ImmutableTimestampMixin


class DeploymentAttribution(ImmutableTimestampMixin, Base):
    __tablename__ = "deployment_attributions"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment_events.id"), primary_key=True
    )
    pr_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pull_requests.id"), primary_key=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
