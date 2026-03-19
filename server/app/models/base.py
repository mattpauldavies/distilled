from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TZDatetime = Annotated[datetime, mapped_column(DateTime(timezone=True))]


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[TZDatetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[TZDatetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ImmutableTimestampMixin:
    created_at: Mapped[TZDatetime] = mapped_column(server_default=func.now())
