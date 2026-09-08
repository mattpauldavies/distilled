"""Ingests pull_request webhook events into the PullRequest table.

Separate from deployment_service: PR ingestion is its own sub-context
(webhook payload → PullRequest upsert) with no deployment knowledge.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.services.webhook_service import (
    SKIPPED,
    parse_datetime,
    parse_datetime_optional,
    register_handler,
    validate_github_url,
)

logger = logging.getLogger(__name__)

HANDLED_PR_ACTIONS = {"opened", "reopened", "closed", "converted_to_draft", "ready_for_review"}


@register_handler("pull_request")
async def handle_pull_request_event(payload: dict, session: AsyncSession) -> str | None:
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})

    if action not in HANDLED_PR_ACTIONS:
        return SKIPPED

    repo_data = payload["repository"]

    # Look up repo by GitHub ID — globally unique, tenant derived from repo
    result = await session.execute(select(Repository).where(Repository.github_id == repo_data["id"]))
    repo = result.scalar_one_or_none()
    if not repo:
        logger.warning("repo not found for PR, github_id=%s", repo_data["id"])
        return SKIPPED

    tenant_id = repo.tenant_id

    merged_at = parse_datetime_optional(pr_data.get("merged_at"))
    opened_at = parse_datetime(pr_data.get("created_at", ""))
    is_draft = pr_data.get("draft", False)
    is_merged = action == "closed" and pr_data.get("merged", False)

    # Determine closed_at
    closed_at = None
    if action == "closed" and not is_merged:
        closed_at = parse_datetime_optional(pr_data.get("closed_at")) or datetime.now(tz=UTC)

    # Determine field overrides based on action
    if action == "converted_to_draft":
        is_draft = True
    elif action == "ready_for_review":
        is_draft = False
    elif action == "reopened":
        closed_at = None
        merged_at = None

    merge_commit_sha = pr_data.get("merge_commit_sha") or None

    stmt = (
        insert(PullRequest)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_id=repo.id,
            github_id=pr_data["id"],
            number=pr_data["number"],
            title=pr_data.get("title", ""),
            base_ref=pr_data.get("base", {}).get("ref", ""),
            merged_at=merged_at,
            merge_commit_sha=merge_commit_sha,
            head_sha=pr_data.get("head", {}).get("sha", ""),
            author_login=pr_data.get("user", {}).get("login", ""),
            html_url=validate_github_url(pr_data.get("html_url", "")),
            opened_at=opened_at,
            is_draft=is_draft,
            closed_at=closed_at,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "repo_id", "number"],
            set_={
                "title": pr_data.get("title", ""),
                "merged_at": merged_at,
                "merge_commit_sha": merge_commit_sha,
                "opened_at": opened_at,
                "is_draft": is_draft,
                "closed_at": closed_at,
            },
        )
    )
    await session.execute(stmt)
    return None
