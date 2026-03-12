# Live Metrics

**Goal:** On-demand metrics for open PRs and PR ageing, computed at request time with no pre-aggregation.

**Scope expansion from PRD:** The existing webhook only captures PRs on merge. This RFC adds PR ingestion on open/update/close events and an `is_draft` flag to support open PR tracking.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest, Alembic

---

## Design

### Model Changes

Add two columns to `pull_requests`:

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `is_draft` | `Boolean` | `False` | Draft status from GitHub |
| `closed_at` | `DateTime(tz)` | `NULL` | Set when PR closed without merge |

**PR states derived from existing + new columns:**

| State | Condition |
|-------|-----------|
| Open (all) | `merged_at IS NULL AND closed_at IS NULL` |
| Live | Open + `is_draft = False` |
| Draft | Open + `is_draft = True` |
| Merged | `merged_at IS NOT NULL` |
| Closed (unmerged) | `closed_at IS NOT NULL AND merged_at IS NULL` |

Migration adds columns with defaults so existing merged PR rows get `is_draft=False, closed_at=NULL`.

### Webhook Expansion

Expand `pull_request` webhook handler beyond `closed+merged`:

| Action | Behavior |
|--------|----------|
| `opened` | Upsert PR row (`merged_at=NULL, closed_at=NULL, is_draft=pr_data["draft"]`) |
| `reopened` | Set `closed_at=NULL, merged_at=NULL` |
| `converted_to_draft` | Set `is_draft=True` |
| `ready_for_review` | Set `is_draft=False` |
| `closed` + `merged=true` | Existing behavior: set `merged_at` |
| `closed` + `merged=false` | Set `closed_at=timestamp` |

All actions use existing `on_conflict_do_update` keyed on `(tenant_id, repo_id, number)`.

### Endpoint: Open PR Counts

`GET /api/metrics/open-prs?repo_id=<UUID>`

```python
class OpenPRsResponse(BaseModel):
    total: int    # all open PRs
    live: int     # non-draft open PRs
    draft: int    # draft open PRs
```

Single query with `COUNT(*)` + conditional `SUM(CASE WHEN is_draft...)`. Scoped to `tenant_id + repo_id + base_ref=default_branch`.

### Endpoint: PR Ageing

`GET /api/metrics/pr-ageing?repo_id=<UUID>`

```python
class AgeBucket(BaseModel):
    bucket: str   # "<2d", "2-7d", "7-14d", ">14d"
    count: int

class PRAgeingResponse(BaseModel):
    buckets: list[AgeBucket]
```

Single query on **live PRs only** (non-draft, open). Bucketed via SQL `CASE WHEN NOW() - opened_at < interval '2 days' THEN '<2d' ...`, `GROUP BY bucket`.

### Performance

Both endpoints target <100ms. Indexes needed:

- `(tenant_id, repo_id, merged_at)` — may already exist
- `(tenant_id, repo_id, closed_at)` — for open PR filtering
- `(tenant_id, repo_id, is_draft)` — optional, for draft filtering

### Not Included

- Percentiles
- Historical trends
- Caching or pre-aggregation
