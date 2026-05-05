import uuid
from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

Role = Literal["owner", "member"]


class TenantUser(TimestampMixin, Base):
    __tablename__ = "tenant_users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_users_tenant_user"),
        CheckConstraint("role IN ('owner','member')", name="ck_tenant_users_role"),
        Index(
            "uq_tenant_users_one_owner",
            "tenant_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )
