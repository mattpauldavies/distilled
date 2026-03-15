# RFC 012: Demo Data Seed

## Summary

Add an optional, opt-in demo data seed for local development and product demos. Running `make seed-demo` populates the database with 6 months of realistic GitHub delivery data for a fictional engineering org (`acme-corp`). Running `make seed-reset` removes it cleanly. No impact on normal installs.

## Decisions

- **Mechanism:** Standalone Python scripts (`server/scripts/seed_demo.py`, `server/scripts/reset_demo.py`) invoked via `make` targets. Not an Alembic migration.
- **Idempotent:** Script checks for an existing row in `github_installations` WHERE `account_login = 'acme-corp'` before inserting. Safe to re-run. To refresh stale data, run `make seed-reset` first.
- **Isolated tenant:** Demo data uses a dedicated fixed UUID tenant (`00000000-0000-0000-0000-000000000001`) same as the dev tenant.
- **Metrics population:** After inserting raw events, the script directly inserts pre-computed metrics rows (deployment_daily_metrics, lead_time_weekly_metrics, pr_cycle_time_weekly_metrics, pr_throughput_weekly_metrics). `metrics_refresh_log` is left empty — the background worker will populate it on next run and will not overwrite pre-seeded metrics.
- **Data range:** 6 months back from the date the script is run.
- **Async entry point:** Scripts use `asyncio.run(main())`. The SQLAlchemy async engine is created inside `main()` to ensure it is bound to the correct event loop.
- **Module resolution:** Make targets set `PYTHONPATH=.` and use `poetry run` so `app.*` imports resolve correctly.

## Fictional Org

**Company:** Acme Corp
**GitHub org:** `acme-corp`
**Installation ID:** `99000001` (fake)

### Repositories

| Repo        | Full name       | Story                                                                    |
| ----------- | --------------- | ------------------------------------------------------------------------ |
| Frontend    | `acme-corp/web` | Steady, healthy team throughout all 6 months                             |
| Backend API | `acme-corp/api` | Starts healthy, hits a rough patch in months 3–4, recovers in months 5–6 |

Each repo has one environment named `production` with `is_production = true`. The link between `deployment_events` and environments is name-based (`environment_name` string column), not a FK — no `environment_id` to populate.

### Engineers

**`acme-corp/web`:** `sarah-chen`, `james-okafor`, `priya-patel`, `tom-harris`
**`acme-corp/api`:** `marcus-webb`, `aisha-johnson`, `dev-lin`

## Data Shape

### `acme-corp/web` — Steady & Healthy

Consistent throughout all 6 months:

| Metric                 | Value            |
| ---------------------- | ---------------- |
| Deployment frequency   | 4–5 deploys/week |
| Lead time (median)     | 1–2 days         |
| PR cycle time (median) | 4–8 hours        |
| PR throughput          | 8–12 PRs/week    |

### `acme-corp/api` — Rough Patch Story

| Phase         | Period     | Deploys/week | Lead time  | Cycle time | Notes                        |
| ------------- | ---------- | ------------ | ---------- | ---------- | ---------------------------- |
| Healthy       | Months 1–2 | 3–4          | 1–2 days   | 6–12 hrs   | Normal delivery              |
| Deteriorating | Month 3    | 1–2          | 5–7 days   | 2–4 days   | Team stretched, large PRs    |
| Rough patch   | Month 4    | 0–1          | 10–14 days | 7–10 days  | Near-zero deploys, PRs aging |
| Recovery      | Month 5    | 2–3          | 3–5 days   | 1–2 days   | Smaller PRs, pace picking up |
| Healthy       | Month 6    | 3–4          | 1–2 days   | 6–12 hrs   | Back to normal               |

Note: Month 4 may produce zero deployments in some weeks. The dashboard must handle sparse data gracefully (this is a known stress case for chart rendering).

## PR Field Conventions

All generated PRs use these fixed conventions:

- `base_ref`: `"main"`
- `head_sha`: deterministic 40-char hex string (see generation detail below)
- `merge_commit_sha`: deterministic 40-char hex string (nullable; set for merged PRs)
- `html_url`: `"https://github.com/<full_name>/pull/<number>"`
- `is_draft`: `False`
- `closed_at`: same as `merged_at` for merged PRs; `None` for open PRs
- `number`: sequential from 1 per repo, deterministic across re-seeds

## PR Titles (examples)

**`acme-corp/web`:** `feat: add user onboarding flow`, `fix: resolve timezone display bug`, `chore: upgrade React to 19`, `feat: dark mode support`, `fix: mobile nav overflow`, `feat: improve search performance`, `fix: handle empty state in activity feed`, `chore: update CI pipeline`

**`acme-corp/api` healthy:** `feat: add rate limiting`, `fix: auth token refresh`, `chore: update dependencies`, `feat: add webhook retry logic`, `fix: improve error messages`

**`acme-corp/api` rough patch:** `refactor: migrate auth to new provider`, `chore: database schema overhaul`, `feat: rewrite job queue`, `fix: resolve data migration issues`, `chore: upgrade ORM version`, `refactor: consolidate API handlers`

## File Structure

```
server/scripts/
├── seed_demo.py       # insert demo data
└── reset_demo.py      # delete all demo data by tenant_id
```

## Make Targets

```makefile
seed-demo:   ## Seed the database with realistic demo data
	cd server && PYTHONPATH=. poetry run python scripts/seed_demo.py

seed-reset:  ## Remove all demo data from the database
	cd server && PYTHONPATH=. poetry run python scripts/reset_demo.py
```

## Data Generation Detail

- **GitHub IDs / deployment IDs:** Start at `9_000_000`, incrementing. Deterministic across re-seeds.
- **PR numbers:** Sequential from `1` per repo, deterministic.
- **Commit SHAs / head SHAs:** Deterministic 40-char hex derived from `hashlib.sha1(f"{repo}:{sequence}".encode()).hexdigest()`.
- **PR → deployment attribution:** Each deployment is linked to PRs merged in the preceding 24-hour window, matching the real attribution heuristic.
- **Metrics tables:** Inserted directly per-week (lead_time, cycle_time, throughput) and per-day (deployments). Values are computed from the generated PR/deployment data to ensure chart accuracy.

## FK-Safe Delete Order (reset_demo.py)

Delete tables in this order to satisfy all foreign key constraints:

1. `deployment_attributions`
2. `deployment_daily_metrics`
3. `lead_time_weekly_metrics`
4. `pr_cycle_time_weekly_metrics`
5. `pr_throughput_weekly_metrics`
6. `metrics_refresh_log`
7. `deployment_events`
8. `pull_requests`
9. `environments`
10. `repositories`
11. `github_installations`
12. `tenants`

## Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `make seed-demo` / `make seed-reset` commands that populate the database with 6 months of realistic Acme Corp engineering data, and remove it cleanly.

**Architecture:** Two standalone Python scripts (`server/scripts/seed_demo.py`, `server/scripts/reset_demo.py`) that create their own SQLAlchemy async engine and operate independently of the running app. The seed generates ~26 weeks of PRs and deployments for two repos (`acme-corp/web` steady, `acme-corp/api` with a rough-patch story arc), then computes and inserts pre-aggregated metrics rows so the dashboard renders immediately. Both scripts are idempotent and isolated from real data via the `account_login = 'acme-corp'` sentinel on `github_installations`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async (asyncpg), FastAPI app models (reused), `asyncio.run()`, `statistics.median`, `random.Random(42)` for determinism.

---

### Chunk 1: seed_demo.py and Makefile targets

#### Task 1: Create the seed script

**Files:**
- Create: `server/scripts/seed_demo.py`

This script inserts all demo data in one transaction. Key design decisions:
- Engine created **inside** `main()` (not at module level) to avoid asyncpg event-loop binding issues
- All IDs are assigned explicitly at object construction (not relying on `flush()` to trigger defaults) so they're available immediately for attribution linking
- PRs are generated such that `merged_at` falls **within** the week, with `opened_at = merged_at - cycle_time`. This makes weekly metrics grouping straightforward.
- `random.Random(42)` makes generation deterministic so re-seeding after reset produces identical data

- [ ] **Step 1: Create `server/scripts/` directory and the script file**

```bash
mkdir -p server/scripts
touch server/scripts/seed_demo.py
```

- [ ] **Step 2: Write the complete seed script**

Write `server/scripts/seed_demo.py` with the following complete content:

```python
"""Seed the database with realistic demo data for Acme Corp.

Usage:
    cd server && PYTHONPATH=. poetry run python scripts/seed_demo.py

To reset:
    make seed-reset
"""

import asyncio
import hashlib
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
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
    PRCycleTimeWeeklyMetric,
    PRThroughputWeeklyMetric,
)
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.tenant import Tenant

# ── Fixed IDs ────────────────────────────────────────────────────────────────

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
INSTALLATION_UUID = UUID("00000000-0000-0000-0000-000000000099")
WEB_REPO_ID = UUID("00000000-0000-0000-0000-000000000010")
API_REPO_ID = UUID("00000000-0000-0000-0000-000000000011")
GITHUB_INSTALLATION_ID = 99_000_001
GITHUB_ID_WEB = 9_000_001
GITHUB_ID_API = 9_000_002

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
    return hashlib.sha1(seed.encode()).hexdigest()


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

        # merged_at: random time within the week
        merged_ts = rng.randint(week_start_ts, week_end_ts)
        merged_at = datetime.fromtimestamp(merged_ts, tz=timezone.utc)

        # opened_at: merged_at minus cycle time
        cycle_secs = rng.randint(cycle_min_secs, cycle_max_secs)
        opened_at = merged_at - timedelta(seconds=cycle_secs)

        prs.append(
            PullRequest(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                repo_id=repo_id,
                github_id=9_000_000 + number,
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
        cycle_secs = sorted(
            (pr.merged_at - pr.opened_at).total_seconds() for pr in week_prs
        )
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
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Idempotency check
        result = await session.execute(
            select(GitHubInstallation).where(
                GitHubInstallation.account_login == "acme-corp"
            )
        )
        if result.scalar_one_or_none() is not None:
            print("Demo data already exists. Run `make seed-reset` first to refresh.")
            await engine.dispose()
            return

        rng = random.Random(42)
        now = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        )

        # ── Ensure dev tenant exists (created by migration, but check defensively) ──
        existing_tenant = await session.get(Tenant, TENANT_ID)
        if existing_tenant is None:
            session.add(Tenant(id=TENANT_ID, name="dev"))

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
            session.add(
                Environment(
                    tenant_id=TENANT_ID,
                    repo_id=rc["id"],
                    name="production",
                    is_production=True,
                )
            )

        # ── Generate 26 weeks of data ─────────────────────────────────────────
        web_prs: list[PullRequest] = []
        api_prs: list[PullRequest] = []
        web_deployments: list[ProductionDeploymentEvent] = []
        api_deployments: list[ProductionDeploymentEvent] = []

        web_pr_counter = [1]
        api_pr_counter = [1]
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
            api_titles = (
                API_TITLES_ROUGH
                if phase in ("deteriorating", "rough_patch")
                else API_TITLES_HEALTHY
            )
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

        # ── Persist PRs and deployments ───────────────────────────────────────
        for pr in web_prs + api_prs:
            session.add(pr)
        for deploy in web_deployments + api_deployments:
            session.add(deploy)

        # ── Attributions ──────────────────────────────────────────────────────
        web_attributions = _build_attributions(TENANT_ID, web_prs, web_deployments)
        api_attributions = _build_attributions(TENANT_ID, api_prs, api_deployments)
        for attr in web_attributions + api_attributions:
            session.add(attr)

        # ── Metrics ───────────────────────────────────────────────────────────
        for metric in _compute_metrics(
            TENANT_ID, WEB_REPO_ID, web_prs, web_deployments, web_attributions
        ):
            session.add(metric)
        for metric in _compute_metrics(
            TENANT_ID, API_REPO_ID, api_prs, api_deployments, api_attributions
        ):
            session.add(metric)

        await session.commit()
        print(
            f"✓ Demo data seeded: "
            f"{len(web_prs + api_prs)} PRs, "
            f"{len(web_deployments + api_deployments)} deployments"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Verify the script runs dry (no DB) with a syntax check**

```bash
cd server && PYTHONPATH=. poetry run python -c "import scripts.seed_demo; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 4: Run the seed script against the local database**

Ensure the DB is up and migrated first (`make db-up && make migrate`), then:

```bash
make seed-demo
```

Expected output:
```
✓ Demo data seeded: NNN PRs, NNN deployments
```
(Exact numbers will vary but should be ~250–390 PRs and ~90–150 deployments)

- [ ] **Step 5: Verify data landed in the DB**

```bash
cd server && PYTHONPATH=. poetry run python -c "
import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import settings
from app.models.repository import Repository
from app.models.pull_request import PullRequest
from app.models.deployment_event import ProductionDeploymentEvent

async def check():
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        repos = (await s.execute(select(func.count()).select_from(Repository))).scalar()
        prs = (await s.execute(select(func.count()).select_from(PullRequest))).scalar()
        deploys = (await s.execute(select(func.count()).select_from(ProductionDeploymentEvent))).scalar()
        print(f'repos={repos}, prs={prs}, deployments={deploys}')
    await engine.dispose()

asyncio.run(check())
"
```

Expected: `repos=2, prs=NNN, deployments=NNN` (non-zero counts)

- [ ] **Step 6: Verify idempotency — running seed-demo again should be a no-op**

```bash
make seed-demo
```

Expected:
```
Demo data already exists. Run `make seed-reset` first to refresh.
```

- [ ] **Step 7: Commit**

```bash
git add server/scripts/seed_demo.py
git commit -m "feat: add demo data seed script"
```

---

#### Task 2: Add Makefile targets

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add seed-demo and seed-reset to the .PHONY line**

In `Makefile`, change line 1 from:
```
.PHONY: dev dev-server dev-client db-up db-down db-reset migrate create-migration test test-server test-client test-coverage
```
to:
```
.PHONY: dev dev-server dev-client db-up db-down db-reset migrate create-migration test test-server test-client test-coverage seed-demo seed-reset
```

- [ ] **Step 2: Append the two targets at the end of the Makefile**

Add after the last target:
```makefile
seed-demo:  ## Seed the database with realistic demo data
	cd server && PYTHONPATH=. poetry run python scripts/seed_demo.py

seed-reset:  ## Remove all demo data from the database
	cd server && PYTHONPATH=. poetry run python scripts/reset_demo.py
```

Note: recipe lines use a **tab** character, not spaces (make requirement).

- [ ] **Step 3: Verify the targets are listed by make**

```bash
make -n seed-demo
```

Expected: prints the command without executing it (no error)

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "feat: add seed-demo and seed-reset make targets"
```

---

### Chunk 2: reset_demo.py and documentation

#### Task 3: Create the reset script

**Files:**
- Create: `server/scripts/reset_demo.py`

The reset script scopes all deletions to the demo installation's repos (not the whole tenant), since the tenant UUID is shared with the dev tenant.

- [ ] **Step 1: Write the reset script**

Write `server/scripts/reset_demo.py` with the following complete content:

```python
"""Remove all demo data seeded by seed_demo.py.

Usage:
    cd server && PYTHONPATH=. poetry run python scripts/reset_demo.py
"""

import asyncio
from uuid import UUID

from sqlalchemy import delete, select
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

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


async def main() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Find the demo installation by sentinel value
        result = await session.execute(
            select(GitHubInstallation).where(
                GitHubInstallation.account_login == "acme-corp",
                GitHubInstallation.tenant_id == TENANT_ID,
            )
        )
        installation = result.scalar_one_or_none()

        if installation is None:
            print("No demo data found.")
            await engine.dispose()
            return

        installation_uuid = installation.id

        # Collect demo repo IDs (scoped to this installation)
        repo_result = await session.execute(
            select(Repository.id).where(
                Repository.installation_id == installation_uuid
            )
        )
        repo_ids = [row[0] for row in repo_result.all()]

        if repo_ids:
            # Collect deployment IDs for attribution deletion
            deploy_result = await session.execute(
                select(ProductionDeploymentEvent.id).where(
                    ProductionDeploymentEvent.repo_id.in_(repo_ids)
                )
            )
            deploy_ids = [row[0] for row in deploy_result.all()]

            # Delete in FK-safe order, scoped to demo repos/deployments
            if deploy_ids:
                await session.execute(
                    delete(DeploymentAttribution).where(
                        DeploymentAttribution.deployment_id.in_(deploy_ids)
                    )
                )
            await session.execute(
                delete(DeploymentDailyMetric).where(
                    DeploymentDailyMetric.repo_id.in_(repo_ids)
                )
            )
            await session.execute(
                delete(LeadTimeWeeklyMetric).where(
                    LeadTimeWeeklyMetric.repo_id.in_(repo_ids)
                )
            )
            await session.execute(
                delete(PRCycleTimeWeeklyMetric).where(
                    PRCycleTimeWeeklyMetric.repo_id.in_(repo_ids)
                )
            )
            await session.execute(
                delete(PRThroughputWeeklyMetric).where(
                    PRThroughputWeeklyMetric.repo_id.in_(repo_ids)
                )
            )
            await session.execute(
                delete(MetricsRefreshLog).where(
                    MetricsRefreshLog.repo_id.in_(repo_ids)
                )
            )
            await session.execute(
                delete(ProductionDeploymentEvent).where(
                    ProductionDeploymentEvent.repo_id.in_(repo_ids)
                )
            )
            await session.execute(
                delete(PullRequest).where(PullRequest.repo_id.in_(repo_ids))
            )
            await session.execute(
                delete(Environment).where(Environment.repo_id.in_(repo_ids))
            )
            await session.execute(
                delete(Repository).where(Repository.id.in_(repo_ids))
            )

        # Delete the installation (but NOT the tenant — it's shared with dev)
        await session.execute(
            delete(GitHubInstallation).where(
                GitHubInstallation.id == installation_uuid
            )
        )

        await session.commit()
        print(f"✓ Demo data removed ({len(repo_ids)} repos).")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify the script runs dry (syntax check)**

```bash
cd server && PYTHONPATH=. poetry run python -c "import scripts.reset_demo; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 3: Run the reset script**

```bash
make seed-reset
```

Expected:
```
✓ Demo data removed (2 repos).
```

- [ ] **Step 4: Verify the DB is clean**

```bash
cd server && PYTHONPATH=. poetry run python -c "
import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import settings
from app.models.repository import Repository
from app.models.pull_request import PullRequest
from app.models.deployment_event import ProductionDeploymentEvent
from app.models.github_installation import GitHubInstallation

async def check():
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        repos = (await s.execute(select(func.count()).select_from(Repository))).scalar()
        prs = (await s.execute(select(func.count()).select_from(PullRequest))).scalar()
        installs = (await s.execute(select(func.count()).select_from(GitHubInstallation).where(GitHubInstallation.account_login == 'acme-corp'))).scalar()
        print(f'repos={repos}, prs={prs}, acme-corp installs={installs}')
    await engine.dispose()

asyncio.run(check())
"
```

Expected: `repos=0, prs=0, acme-corp installs=0`

- [ ] **Step 5: Verify seed → reset → seed cycle works (full idempotency)**

```bash
make seed-demo && make seed-reset && make seed-demo
```

Expected: first and third commands print success with counts; second prints removal message.

- [ ] **Step 6: Commit**

```bash
git add server/scripts/reset_demo.py
git commit -m "feat: add demo data reset script"
```

---

#### Task 4: Update documentation

**Files:**
- Modify: `docs/runbooks/local-setup.md`

- [ ] **Step 1: Add a "Demo Data" section to local-setup.md**

Insert a new section after the existing "## 1. Start the Database" section (before "## 2. Create a GitHub App"). Add:

```markdown
---

## 2. (Optional) Seed Demo Data

If you want to explore the product without setting up a real GitHub App, you can seed the database with 6 months of realistic demo data for a fictional org (`acme-corp`):

```sh
make seed-demo
```

This creates two repositories (`acme-corp/web` and `acme-corp/api`) with realistic PR and deployment history. `acme-corp/api` includes a rough-patch story arc (healthy → deteriorates → recovers) to demonstrate the full range of metrics.

To remove the demo data:

```sh
make seed-reset
```

To refresh with a clean set (e.g. after time has passed and dates look stale):

```sh
make seed-reset && make seed-demo
```

> **Note:** Demo data is isolated from any real GitHub data you connect later. Connecting a real GitHub App will add your real repos alongside the demo repos — run `make seed-reset` first if you want a clean install.

---
```

Renumber all subsequent `##` headings: "2. Create a GitHub App" → "3. Create a GitHub App", through to the end of the numbered sections.

- [ ] **Step 2: Verify the file renders correctly**

```bash
cat -n docs/runbooks/local-setup.md | head -60
```

Expected: numbered sections visible and sequential.

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/local-setup.md
git commit -m "docs: add demo data seed instructions to local setup runbook"
```
