"""Nightly invitation expiry.

Calls the server's janitor endpoint, which revokes invitations that passed
their TTL without being redeemed.

This is a Python script rather than a `curl` one-liner in the Railway start
command because the runtime image (`server/Dockerfile`) ships no `curl`.

Usage:
    cd server && API_BASE_URL=http://localhost:8000 \
        INTERNAL_CRON_SECRET=... \
        poetry run python scripts/expire_invitations.py

Exit codes:
    0 — the janitor ran.
    1 — missing config, or the endpoint was unreachable or returned an error.
"""

import os
import sys

import httpx

TIMEOUT_S = float(os.environ.get("EXPIRE_TIMEOUT_S", "30"))


def expire(client: httpx.Client) -> int:
    resp = client.post("/internal/invitations/expire")
    resp.raise_for_status()
    return resp.json()["expired"]


def run() -> int:
    base_url = os.environ["API_BASE_URL"]
    secret = os.environ["INTERNAL_CRON_SECRET"]

    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=TIMEOUT_S,
    ) as client:
        return expire(client)


def main() -> int:
    if not os.environ.get("API_BASE_URL") or not os.environ.get("INTERNAL_CRON_SECRET"):
        print("API_BASE_URL and INTERNAL_CRON_SECRET must be set", file=sys.stderr)
        return 1
    try:
        expired = run()
    except (httpx.HTTPError, KeyError) as exc:
        print(f"invitation expiry failed: {exc}", file=sys.stderr)
        return 1
    print(f"invitation_expiry_complete expired={expired}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
