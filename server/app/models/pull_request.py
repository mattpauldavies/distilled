import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, TZDatetime


class PullRequest(TimestampMixin, Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"))
    github_id: Mapped[int] = mapped_column(BigInteger)
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(1024))
    base_ref: Mapped[str] = mapped_column(String(255))
    merged_at: Mapped[TZDatetime]
    opened_at: Mapped[TZDatetime | None] = mapped_column(nullable=True)
    merge_commit_sha: Mapped[str] = mapped_column(String(40))
    head_sha: Mapped[str] = mapped_column(String(40))
    author_login: Mapped[str] = mapped_column(String(255))
    html_url: Mapped[str] = mapped_column(String(2048), default="")
