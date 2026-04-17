"""Hourly batch metrics recompute.

Enumerates all (tenant_id, repo_id) pairs via the server's internal API, then
fans out per-repo recompute calls with bounded concurrency and small jitter.

Usage:
    cd server && APP_BASE_URL=http://localhost:8000 \
        INTERNAL_CRON_SECRET=... \
        PYTHONPATH=. poetry run python scripts/run_hourly_recompute.py
"""

import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass

import httpx


@dataclass
class RunSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duration_s: float = 0.0


async def fetch_targets(client: httpx.AsyncClient) -> list[dict]:
    raise NotImplementedError


async def recompute_one(client: httpx.AsyncClient, target: dict) -> bool:
    raise NotImplementedError


async def run() -> RunSummary:
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
