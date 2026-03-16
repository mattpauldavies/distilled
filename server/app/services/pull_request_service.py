import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest
from app.models.repository import Repository


def _ageing_bucket_expr():
    """SQL CASE expression for PR age buckets. Single definition — no duplication."""
    now = func.now()
    age = now - PullRequest.opened_at
    return sa.case(
        (age < sa.text("interval '2 days'"), sa.literal("<2d")),
        (age < sa.text("interval '7 days'"), sa.literal("2-7d")),
        (age < sa.text("interval '14 days'"), sa.literal("7-14d")),
        else_=sa.literal(">14d"),
    ).label("bucket")


async def get_open_pr_count(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
) -> dict:
    result = await session.execute(
        select(
            func.count().label("total"),
            func.sum(func.cast(PullRequest.is_draft == False, sa.Integer)).label("live"),
            func.sum(func.cast(PullRequest.is_draft == True, sa.Integer)).label("draft"),
        ).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo.id,
            PullRequest.base_ref == repo.default_branch,
            PullRequest.merged_at.is_(None),
            PullRequest.closed_at.is_(None),
        )
    )
    row = result.one()
    return {
        "total": row.total or 0,
        "live": row.live or 0,
        "draft": row.draft or 0,
    }


async def get_pr_ageing(
    tenant_id: uuid.UUID,
    repo: Repository,
    session: AsyncSession,
) -> list[dict]:
    bucket_expr = _ageing_bucket_expr()

    result = await session.execute(
        select(
            bucket_expr,
            func.count().label("count"),
        ).where(
            PullRequest.tenant_id == tenant_id,
            PullRequest.repo_id == repo.id,
            PullRequest.base_ref == repo.default_branch,
            PullRequest.merged_at.is_(None),
            PullRequest.closed_at.is_(None),
            PullRequest.is_draft.is_(False),
        ).group_by(sa.text("bucket"))
    )
    _order = {"<2d": 0, "2-7d": 1, "7-14d": 2, ">14d": 3}
    rows = sorted(result.all(), key=lambda r: _order.get(r.bucket, 99))
    return [{"bucket": row.bucket, "count": row.count} for row in rows]
