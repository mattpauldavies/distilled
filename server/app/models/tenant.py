import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    rename_prompt_dismissed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
