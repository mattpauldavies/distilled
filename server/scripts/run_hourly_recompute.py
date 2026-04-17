"""Hourly batch metrics recompute.

Enumerates all (tenant_id, repo_id) pairs via the server's internal API, then
fans out per-repo recompute calls with bounded concurrency and small jitter.

Usage:
    cd server && APP_BASE_URL=http://localhost:8000 \
        INTERNAL_CRON_SECRET=... \
        PYTHONPATH=. poetry run python scripts/run_hourly_recompute.py

Exit codes:
    0 — run completed (per-repo failures are reported, not raised).
    1 — scheduler-level failure (missing config, enumeration unreachable).
"""

import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass

import httpx

JITTER_MS = int(os.environ.get("RECOMPUTE_JITTER_MS", "2000"))
CONCURRENCY = int(os.environ.get("RECOMPUTE_CONCURRENCY", "3"))
TIMEOUT_S = float(os.environ.get("RECOMPUTE_TIMEOUT_S", "120"))
RETRY_DELAY_S = 5.0


@dataclass
class RunSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duration_s: float = 0.0


async def fetch_targets(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get("/metrics/recompute-targets")
    resp.raise_for_status()
    return resp.json()["targets"]


async def recompute_one(client: httpx.AsyncClient, target: dict) -> bool:
    for attempt in range(2):  # initial + one retry
        try:
            resp = await client.post("/metrics/recompute", json=target, timeout=TIMEOUT_S)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            if attempt == 0:
                await asyncio.sleep(RETRY_DELAY_S)
                continue
            return False
        if resp.status_code >= 500 and attempt == 0:
            await asyncio.sleep(RETRY_DELAY_S)
            continue
        return resp.status_code == 200
    return False


async def _with_jitter(
    target: dict, client: httpx.AsyncClient, sem: asyncio.Semaphore
) -> bool:
    async with sem:
        if JITTER_MS > 0:
            await asyncio.sleep(random.uniform(0, JITTER_MS / 1000))
        return await recompute_one(client, target)


async def run() -> RunSummary:
    base_url = os.environ["APP_BASE_URL"]
    secret = os.environ["INTERNAL_CRON_SECRET"]

    started = time.monotonic()
    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=TIMEOUT_S,
    ) as client:
        targets = await fetch_targets(client)
        sem = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(
            *(_with_jitter(t, client, sem) for t in targets),
        )

    succeeded = sum(1 for ok in results if ok)
    return RunSummary(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        duration_s=time.monotonic() - started,
    )


def main() -> int:
    if not os.environ.get("APP_BASE_URL") or not os.environ.get("INTERNAL_CRON_SECRET"):
        print("APP_BASE_URL and INTERNAL_CRON_SECRET must be set", file=sys.stderr)
        return 1
    try:
        summary = asyncio.run(run())
    except (httpx.HTTPError, KeyError) as exc:
        print(f"enumeration failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"recompute_run_complete total={summary.total} succeeded={summary.succeeded} "
        f"failed={summary.failed} duration_s={summary.duration_s:.1f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
