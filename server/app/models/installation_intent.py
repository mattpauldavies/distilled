import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InstallationIntent(TimestampMixin, Base):
    """A short-lived, single-use claim: "user U is connecting an installation to workspace W".

    Minted before redirecting to GitHub (the raw nonce travels as GitHub's
    ``state`` parameter; only its SHA-256 is stored). Consumed by the setup
    callback or by webhook sender matching.
    """

    __tablename__ = "installation_intents"
    __table_args__ = (UniqueConstraint("nonce_hash", name="uq_installation_intents_nonce_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    nonce_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
