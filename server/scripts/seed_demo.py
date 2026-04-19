"""Seed the database with realistic demo data for Acme Corp.

Usage:
    cd server && PYTHONPATH=. poetry run python scripts/seed_demo.py

To reset:
    make seed-reset
"""

import asyncio
import hashlib
import os
import random
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import median
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.deployment_attribution import DeploymentAttribution
from app.models.deployment_event import ProductionDeploymentEvent
from app.models.environment import Environment
from app.models.github_installation import GitHubInstallation
from app.models.metrics import (
    DeploymentDailyMetric,
    LeadTimeWeeklyMetric,
    MetricsRefreshLog,
    PRCycleTimeWeeklyMetric,
    PRThroughputWeeklyMetric,
)
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.tenant import Tenant
from app.models.user import User

# ── Fixed IDs ────────────────────────────────────────────────────────────────

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
INSTALLATION_UUID = UUID("00000000-0000-0000-0000-000000000099")
WEB_REPO_ID = UUID("00000000-0000-0000-0000-000000000010")
API_REPO_ID = UUID("00000000-0000-0000-0000-000000000011")
GITHUB_INSTALLATION_ID = 99_000_001
GITHUB_ID_WEB = 9_000_001
GITHUB_ID_API = 9_000_002
GITHUB_PR_ID_WEB_START = 9_100_000
GITHUB_PR_ID_API_START = 9_200_000

# ── Content ───────────────────────────────────────────────────────────────────

WEB_TITLES = [
    "feat: add user onboarding flow",
    "fix: resolve timezone display bug",
    "chore: upgrade React to 19",
    "feat: dark mode support",
    "fix: mobile nav overflow",
    "feat: improve search performance",
    "fix: handle empty state in activity feed",
    "chore: update CI pipeline",
    "feat: add keyboard shortcuts",
    "fix: correct chart tooltip formatting",
    "chore: remove deprecated components",
    "feat: add export to CSV",
    "fix: loading spinner flicker on slow connections",
    "feat: add date range filter to reports",
    "chore: add Storybook stories for Card component",
]
WEB_AUTHORS = ["sarah-chen", "james-okafor", "priya-patel", "tom-harris"]

API_TITLES_HEALTHY = [
    "feat: add rate limiting middleware",
    "fix: auth token refresh race condition",
    "chore: update dependencies",
    "feat: add webhook retry logic",
    "fix: improve error response messages",
    "feat: add pagination to list endpoints",
    "fix: handle null values in metrics query",
    "chore: add structured request logging",
    "feat: batch insert for deployment events",
    "fix: timezone handling in attribution window",
]
API_TITLES_ROUGH = [
    "refactor: migrate auth to new provider",
    "chore: database schema overhaul - phase 1",
    "chore: database schema overhaul - phase 2",
    "feat: rewrite job queue with new broker",
    "fix: resolve data migration consistency issues",
    "chore: upgrade ORM to v2",
    "refactor: consolidate API handlers",
    "fix: address performance regression in queries",
    "chore: fix migration rollback procedure",
    "fix: connection pool exhaustion under load",
]
API_AUTHORS = ["marcus-webb", "aisha-johnson", "dev-lin"]

# ── Open / draft PR specs for ageing demo ─────────────────────────────────────
# Each entry: title, author, days_ago (float), is_draft

WEB_OPEN_SPECS = [
    # <2d bucket — live
    dict(title="feat: add user notifications", author="sarah-chen", days_ago=1.0, is_draft=False),
    dict(title="fix: improve dashboard loading performance", author="priya-patel", days_ago=0.75, is_draft=False),
    # <2d bucket — draft
    dict(title="WIP: real-time activity feed", author="james-okafor", days_ago=1.2, is_draft=True),
    # 2-7d bucket — live
    dict(title="feat: new analytics overview page", author="tom-harris", days_ago=4.0, is_draft=False),
    dict(title="chore: update ESLint config", author="sarah-chen", days_ago=5.5, is_draft=False),
    # 7-14d bucket — live
    dict(title="feat: team management settings", author="james-okafor", days_ago=10.0, is_draft=False),
    dict(title="fix: edge case in date range picker", author="priya-patel", days_ago=12.0, is_draft=False),
    # 7-14d bucket — draft
    dict(title="WIP: notification preferences modal", author="tom-harris", days_ago=9.0, is_draft=True),
    # >14d bucket — live
    dict(title="feat: redesign account settings page", author="sarah-chen", days_ago=20.0, is_draft=False),
    dict(title="fix: stale data on page refresh", author="james-okafor", days_ago=22.0, is_draft=False),
    dict(title="feat: add export to PDF", author="tom-harris", days_ago=30.0, is_draft=False),
    # >14d bucket — draft
    dict(title="WIP: data export pipeline", author="priya-patel", days_ago=21.0, is_draft=True),
]

API_OPEN_SPECS = [
    # <2d bucket — live
    dict(title="feat: add GraphQL subscriptions", author="marcus-webb", days_ago=1.0, is_draft=False),
    # 2-7d bucket — live
    dict(title="fix: rate limiter edge case under burst", author="aisha-johnson", days_ago=4.0, is_draft=False),
    dict(title="feat: bulk operations API", author="dev-lin", days_ago=5.5, is_draft=False),
    # 2-7d bucket — draft
    dict(title="WIP: streaming response support", author="marcus-webb", days_ago=4.5, is_draft=True),
    # 7-14d bucket — live
    dict(title="chore: migrate to async job runner", author="aisha-johnson", days_ago=10.0, is_draft=False),
    dict(title="feat: audit log endpoint", author="dev-lin", days_ago=11.0, is_draft=False),
    # >14d bucket — live
    dict(title="fix: connection timeout under load", author="marcus-webb", days_ago=20.0, is_draft=False),
    dict(title="feat: add multi-tenant isolation layer", author="aisha-johnson", days_ago=22.0, is_draft=False),
    dict(title="chore: upgrade PostgreSQL driver", author="marcus-webb", days_ago=32.0, is_draft=False),
    # >14d bucket — draft
    dict(title="WIP: new authentication provider", author="dev-lin", days_ago=21.0, is_draft=True),
]

# ── Phase parameters ──────────────────────────────────────────────────────────


def get_api_phase(weeks_ago: int) -> str:
    """Map weeks_ago (0=this week, 25=6 months ago) to a phase name."""
    if weeks_ago >= 17:
        return "healthy_early"
    elif weeks_ago >= 13:
        return "deteriorating"
    elif weeks_ago >= 9:
        return "rough_patch"
    elif weeks_ago >= 5:
        return "recovery"
    else:
        return "healthy_late"


PHASE_PARAMS: dict[str, dict] = {
    "healthy_early": dict(deploys=(3, 4), cycle_hours=(6, 12), prs=(6, 9)),
    "deteriorating": dict(deploys=(1, 2), cycle_hours=(48, 96), prs=(3, 5)),
    "rough_patch": dict(deploys=(0, 1), cycle_hours=(168, 240), prs=(2, 4)),
    "recovery": dict(deploys=(2, 3), cycle_hours=(24, 48), prs=(5, 7)),
    "healthy_late": dict(deploys=(3, 4), cycle_hours=(6, 12), prs=(6, 9)),
}
WEB_PARAMS = dict(deploys=(4, 5), cycle_hours=(4, 8), prs=(8, 12))

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_sha(seed: str) -> str:
    """Deterministic 40-char hex SHA from a seed string."""
    return hashlib.sha1(seed.encode(), usedforsecurity=False).hexdigest()


def week_monday(dt: datetime) -> date:
    """Return the Monday of the week containing dt."""
    return dt.date() - timedelta(days=dt.weekday())


def _generate_week_prs(
    rng: random.Random,
    repo_id: UUID,
    repo_full_name: str,
    tenant_id: UUID,
    titles: list[str],
    authors: list[str],
    params: dict,
    pr_counter: list[int],
    pr_github_id_counter: list[int],
    week_end: datetime,
) -> list[PullRequest]:
    """Generate PRs whose merged_at falls within the week ending at week_end."""
    pr_count = rng.randint(*params["prs"])
    prs = []
    cycle_min_secs = params["cycle_hours"][0] * 3600
    cycle_max_secs = params["cycle_hours"][1] * 3600
    week_start = week_end - timedelta(days=7)
    week_start_ts = int(week_start.timestamp())
    week_end_ts = int(week_end.timestamp())

    for _ in range(pr_count):
        number = pr_counter[0]
        pr_counter[0] += 1

        github_id = pr_github_id_counter[0]
        pr_github_id_counter[0] += 1

        # merged_at: random time within the week
        merged_ts = rng.randint(week_start_ts, week_end_ts)
        merged_at = datetime.fromtimestamp(merged_ts, tz=UTC)

        # opened_at: merged_at minus cycle time
        cycle_secs = rng.randint(cycle_min_secs, cycle_max_secs)
        opened_at = merged_at - timedelta(seconds=cycle_secs)

        prs.append(
            PullRequest(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                repo_id=repo_id,
                github_id=github_id,
                number=number,
                title=rng.choice(titles),
                base_ref="main",
                opened_at=opened_at,
                merged_at=merged_at,
                merge_commit_sha=make_sha(f"{repo_full_name}:merge:{number}"),
                head_sha=make_sha(f"{repo_full_name}:pr:{number}"),
                author_login=rng.choice(authors),
                html_url=f"https://github.com/{repo_full_name}/pull/{number}",
                is_draft=False,
                closed_at=merged_at,
            )
        )
    return prs


def _generate_week_deployments(
    rng: random.Random,
    repo_id: UUID,
    tenant_id: UUID,
    params: dict,
    deploy_counter: list[int],
    week_start: datetime,
    week_end: datetime,
) -> list[ProductionDeploymentEvent]:
    """Generate deployments spread across the week."""
    deploy_count = rng.randint(*params["deploys"])
    deployments = []
    week_secs = int((week_end - week_start).total_seconds())

    for _ in range(deploy_count):
        dep_id = deploy_counter[0]
        deploy_counter[0] += 1

        offset_secs = rng.randint(int(week_secs * 0.1), int(week_secs * 0.9))
        deployed_at = week_start + timedelta(seconds=offset_secs)

        deployments.append(
            ProductionDeploymentEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                repo_id=repo_id,
                environment_name="production",
                deployment_id=dep_id,
                commit_sha=make_sha(f"deploy:{dep_id}"),
                ref="main",
                started_at=deployed_at - timedelta(minutes=5),
                completed_at=deployed_at,
                deployed_at=deployed_at,
                html_url=f"https://github.com/runs/{dep_id}",
            )
        )
    return deployments


def _generate_open_prs(
    repo_id: UUID,
    repo_full_name: str,
    tenant_id: UUID,
    pr_counter: list[int],
    pr_github_id_counter: list[int],
    now: datetime,
    specs: list[dict],
) -> list[PullRequest]:
    """Generate open (unmerged, unclosed) PRs at fixed ages relative to now."""
    prs = []
    for spec in specs:
        number = pr_counter[0]
        pr_counter[0] += 1
        github_id = pr_github_id_counter[0]
        pr_github_id_counter[0] += 1
        opened_at = now - timedelta(days=spec["days_ago"])
        prs.append(
            PullRequest(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                repo_id=repo_id,
                github_id=github_id,
                number=number,
                title=spec["title"],
                base_ref="main",
                opened_at=opened_at,
                merged_at=None,
                merge_commit_sha=None,
                head_sha=make_sha(f"{repo_full_name}:open:{number}"),
                author_login=spec["author"],
                html_url=f"https://github.com/{repo_full_name}/pull/{number}",
                is_draft=spec["is_draft"],
                closed_at=None,
            )
        )
    return prs


def _build_attributions(
    tenant_id: UUID,
    all_prs: list[PullRequest],
    deployments: list[ProductionDeploymentEvent],
) -> list[DeploymentAttribution]:
    """Link each deployment to PRs merged in the preceding 24 hours."""
    attributions = []
    for deploy in deployments:
        window_start = deploy.deployed_at - timedelta(hours=24)
        for pr in all_prs:
            if pr.merged_at and window_start <= pr.merged_at <= deploy.deployed_at:
                attributions.append(
                    DeploymentAttribution(
                        deployment_id=deploy.id,
                        pr_id=pr.id,
                        tenant_id=tenant_id,
                    )
                )
    return attributions


def _compute_metrics(
    tenant_id: UUID,
    repo_id: UUID,
    all_prs: list[PullRequest],
    deployments: list[ProductionDeploymentEvent],
    attributions: list[DeploymentAttribution],
) -> list:
    """Compute all metrics rows from generated data."""
    metrics: list = []

    # Build PR → first deployment lookup from attributions
    pr_to_first_deploy: dict[UUID, ProductionDeploymentEvent] = {}
    deploy_map = {d.id: d for d in deployments}
    for attr in attributions:
        deploy = deploy_map.get(attr.deployment_id)
        if deploy:
            existing = pr_to_first_deploy.get(attr.pr_id)
            if existing is None or deploy.deployed_at < existing.deployed_at:
                pr_to_first_deploy[attr.pr_id] = deploy

    # Deployment daily metrics
    daily: defaultdict[date, int] = defaultdict(int)
    for deploy in deployments:
        daily[deploy.deployed_at.date()] += 1
    for day, count in daily.items():
        metrics.append(
            DeploymentDailyMetric(
                tenant_id=tenant_id,
                repo_id=repo_id,
                date=day,
                deployment_count=count,
            )
        )

    # Group merged PRs by ISO week (Monday)
    merged_prs = [pr for pr in all_prs if pr.merged_at]
    weeks: defaultdict[date, list[PullRequest]] = defaultdict(list)
    for pr in merged_prs:
        weeks[week_monday(pr.merged_at)].append(pr)

    for ws, week_prs in weeks.items():
        # Throughput
        metrics.append(
            PRThroughputWeeklyMetric(
                tenant_id=tenant_id,
                repo_id=repo_id,
                week_start=ws,
                pr_count=len(week_prs),
            )
        )

        # PR cycle time
        cycle_secs = sorted((pr.merged_at - pr.opened_at).total_seconds() for pr in week_prs)
        med_cycle = median(cycle_secs)
        p75_cycle = cycle_secs[min(int(len(cycle_secs) * 0.75), len(cycle_secs) - 1)]
        metrics.append(
            PRCycleTimeWeeklyMetric(
                tenant_id=tenant_id,
                repo_id=repo_id,
                week_start=ws,
                median_seconds=med_cycle,
                p75_seconds=p75_cycle,
                sample_size=len(cycle_secs),
            )
        )

        # Lead time (only for PRs attributed to a deployment)
        lead_secs = sorted(
            (pr_to_first_deploy[pr.id].deployed_at - pr.opened_at).total_seconds()
            for pr in week_prs
            if pr.id in pr_to_first_deploy
        )
        if lead_secs:
            med_lead = median(lead_secs)
            p75_lead = lead_secs[min(int(len(lead_secs) * 0.75), len(lead_secs) - 1)]
            metrics.append(
                LeadTimeWeeklyMetric(
                    tenant_id=tenant_id,
                    repo_id=repo_id,
                    week_start=ws,
                    median_seconds=med_lead,
                    p75_seconds=p75_lead,
                    sample_size=len(lead_secs),
                )
            )

    return metrics


async def main() -> None:
    if settings.environment == "production":
        print("FATAL: refusing to run seed script against production database")
        return
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Idempotency check
        result = await session.execute(
            select(GitHubInstallation).where(GitHubInstallation.account_login == "acme-corp")
        )
        if result.scalar_one_or_none() is not None:
            print("Demo data already exists. Run `make seed-reset` first to refresh.")
            await engine.dispose()
            return

        rng = random.Random(42)
        now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)

        # ── Ensure dev tenant exists (created by migration, but check defensively) ──
        existing_tenant = await session.get(Tenant, TENANT_ID)
        if existing_tenant is None:
            session.add(Tenant(id=TENANT_ID, name="dev"))

        # ── Pre-seed smoke test user so sign-in resolves to the seed tenant ──
        # When CLERK_SMOKE_USER_ID is set (CI smoke tests), insert a User row that
        # maps the Clerk test user ID → seed tenant. get_or_create_user_and_tenant
        # will find this row on first login and return the seed tenant, giving the
        # smoke test user access to all demo data without creating a new tenant.
        clerk_smoke_user_id = os.environ.get("CLERK_SMOKE_USER_ID")
        if clerk_smoke_user_id:
            session.add(
                User(
                    id=uuid.uuid4(),
                    clerk_user_id=clerk_smoke_user_id,
                    tenant_id=TENANT_ID,
                )
            )

        # ── Infrastructure rows ───────────────────────────────────────────────
        session.add(
            GitHubInstallation(
                id=INSTALLATION_UUID,
                tenant_id=TENANT_ID,
                installation_id=GITHUB_INSTALLATION_ID,
                account_login="acme-corp",
                account_type="organization",
            )
        )
        repos_config = [
            dict(id=WEB_REPO_ID, github_id=GITHUB_ID_WEB, full_name="acme-corp/web"),
            dict(id=API_REPO_ID, github_id=GITHUB_ID_API, full_name="acme-corp/api"),
        ]
        for rc in repos_config:
            session.add(
                Repository(
                    id=rc["id"],
                    tenant_id=TENANT_ID,
                    installation_id=INSTALLATION_UUID,
                    github_id=rc["github_id"],
                    full_name=rc["full_name"],
                    default_branch="main",
                )
            )

        # Flush so repositories exist before environments (FK dependency)
        await session.flush()

        for rc in repos_config:
            session.add(
                Environment(
                    tenant_id=TENANT_ID,
                    repo_id=rc["id"],
                    name="production",
                    is_production=True,
                )
            )

        # Flush infrastructure rows so FK constraints are satisfied for PRs/deployments
        await session.flush()

        # ── Generate 26 weeks of data ─────────────────────────────────────────
        web_prs: list[PullRequest] = []
        api_prs: list[PullRequest] = []
        web_deployments: list[ProductionDeploymentEvent] = []
        api_deployments: list[ProductionDeploymentEvent] = []

        web_pr_counter = [1]
        api_pr_counter = [1]
        web_pr_github_id_counter = [GITHUB_PR_ID_WEB_START]
        api_pr_github_id_counter = [GITHUB_PR_ID_API_START]
        deploy_counter = [9_000_000]

        for weeks_ago in range(25, -1, -1):
            week_end = now - timedelta(weeks=weeks_ago)
            week_start = week_end - timedelta(days=7)

            web_prs.extend(
                _generate_week_prs(
                    rng=rng,
                    repo_id=WEB_REPO_ID,
                    repo_full_name="acme-corp/web",
                    tenant_id=TENANT_ID,
                    titles=WEB_TITLES,
                    authors=WEB_AUTHORS,
                    params=WEB_PARAMS,
                    pr_counter=web_pr_counter,
                    pr_github_id_counter=web_pr_github_id_counter,
                    week_end=week_end,
                )
            )
            web_deployments.extend(
                _generate_week_deployments(
                    rng=rng,
                    repo_id=WEB_REPO_ID,
                    tenant_id=TENANT_ID,
                    params=WEB_PARAMS,
                    deploy_counter=deploy_counter,
                    week_start=week_start,
                    week_end=week_end,
                )
            )

            phase = get_api_phase(weeks_ago)
            api_params = PHASE_PARAMS[phase]
            api_titles = API_TITLES_ROUGH if phase in ("deteriorating", "rough_patch") else API_TITLES_HEALTHY
            api_prs.extend(
                _generate_week_prs(
                    rng=rng,
                    repo_id=API_REPO_ID,
                    repo_full_name="acme-corp/api",
                    tenant_id=TENANT_ID,
                    titles=api_titles,
                    authors=API_AUTHORS,
                    params=api_params,
                    pr_counter=api_pr_counter,
                    pr_github_id_counter=api_pr_github_id_counter,
                    week_end=week_end,
                )
            )
            api_deployments.extend(
                _generate_week_deployments(
                    rng=rng,
                    repo_id=API_REPO_ID,
                    tenant_id=TENANT_ID,
                    params=api_params,
                    deploy_counter=deploy_counter,
                    week_start=week_start,
                    week_end=week_end,
                )
            )

        # ── Open / draft PRs for ageing demo ─────────────────────────────────
        web_open_prs = _generate_open_prs(
            repo_id=WEB_REPO_ID,
            repo_full_name="acme-corp/web",
            tenant_id=TENANT_ID,
            pr_counter=web_pr_counter,
            pr_github_id_counter=web_pr_github_id_counter,
            now=now,
            specs=WEB_OPEN_SPECS,
        )
        api_open_prs = _generate_open_prs(
            repo_id=API_REPO_ID,
            repo_full_name="acme-corp/api",
            tenant_id=TENANT_ID,
            pr_counter=api_pr_counter,
            pr_github_id_counter=api_pr_github_id_counter,
            now=now,
            specs=API_OPEN_SPECS,
        )

        # ── Persist PRs and deployments ───────────────────────────────────────
        for pr in web_prs + api_prs + web_open_prs + api_open_prs:
            session.add(pr)
        for deploy in web_deployments + api_deployments:
            session.add(deploy)

        # Flush so FK constraints are satisfied when attributions are inserted
        await session.flush()

        # ── Attributions ──────────────────────────────────────────────────────
        web_attributions = _build_attributions(TENANT_ID, web_prs, web_deployments)
        api_attributions = _build_attributions(TENANT_ID, api_prs, api_deployments)
        for attr in web_attributions + api_attributions:
            session.add(attr)

        # ── Metrics ───────────────────────────────────────────────────────────
        for metric in _compute_metrics(TENANT_ID, WEB_REPO_ID, web_prs, web_deployments, web_attributions):
            session.add(metric)
        for metric in _compute_metrics(TENANT_ID, API_REPO_ID, api_prs, api_deployments, api_attributions):
            session.add(metric)

        # ── Metrics refresh log ───────────────────────────────────────────────
        # Mark both repos as freshly refreshed so the dashboard freshness
        # indicator shows "Data current" and the cold-start modal stays hidden.
        refresh_hour = now.replace(minute=0, second=0, microsecond=0)
        for repo_id in (WEB_REPO_ID, API_REPO_ID):
            session.add(
                MetricsRefreshLog(
                    tenant_id=TENANT_ID,
                    repo_id=repo_id,
                    hour=refresh_hour,
                    started_at=now - timedelta(minutes=1),
                    completed_at=now,
                    status="success",
                )
            )

        await session.commit()
        open_pr_count = len(web_open_prs + api_open_prs)
        print(
            f"✓ Demo data seeded: "
            f"{len(web_prs + api_prs)} merged PRs, "
            f"{open_pr_count} open/draft PRs, "
            f"{len(web_deployments + api_deployments)} deployments"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
