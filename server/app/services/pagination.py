"""Shared count-then-page helper for paginated list endpoints."""

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import PaginatedResponse, PaginationParams


async def paginate[SchemaT: BaseModel](
    session: AsyncSession,
    stmt: Select,
    pagination: PaginationParams,
    schema: type[SchemaT],
) -> PaginatedResponse[SchemaT]:
    """Count the full result set, then fetch one offset/limit page of it.

    `stmt` should include filtering and ordering; ordering is stripped for
    the count query.
    """
    count_result = await session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    total = count_result.scalar_one()

    result = await session.execute(stmt.offset(pagination.offset).limit(pagination.limit))
    rows = result.scalars().all()

    return PaginatedResponse(
        items=[schema.model_validate(r) for r in rows],
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )
