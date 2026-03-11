# RFC 006: Deployment Frequency Endpoint

## Summary

Read endpoint exposing pre-computed deployment frequency from `deployment_daily_metrics` (built in RFC 005).

## Endpoint

`GET /api/metrics/deployment-frequency?repo_id=...&days=30`

- `repo_id` required, validated via `get_verified_repo`
- `days` optional (30/60/90, default 30)
- Standard tenant auth

## Response

```json
{
  "status": "ok",
  "total": 42,
  "days": 30,
  "daily_counts": [
    { "date": "2025-01-15", "count": 3 }
  ]
}
```

**Setup state:** If no production environment configured for the repo:
```json
{ "status": "setup_required", "message": "no production environment configured" }
```

**Zero state:** Production env exists but no deployments → `total: 0, daily_counts: []`

## Files

- Modify: `server/app/routes/metrics.py` — add GET endpoint
- Create: `server/app/schemas/metrics.py` — response schemas
- Create: `server/tests/test_deployment_frequency.py` — endpoint tests
