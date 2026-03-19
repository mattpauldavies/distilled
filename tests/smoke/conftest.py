"""Shared fixtures for smoke tests.

Set SMOKE_BASE_URL to target a non-local environment:
    SMOKE_BASE_URL=https://api.example.com pytest tests/smoke/
"""

import os

import httpx
import pytest

# Default to local dev server; override via env var for staging/production
BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")

# Fixed demo seed IDs — these never change
TENANT_ID = "00000000-0000-0000-0000-000000000001"
WEB_REPO_ID = "00000000-0000-0000-0000-000000000010"
API_REPO_ID = "00000000-0000-0000-0000-000000000011"


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as c:
        yield c


@pytest.fixture(scope="session")
def web_repo_id() -> str:
    return WEB_REPO_ID


@pytest.fixture(scope="session")
def api_repo_id() -> str:
    return API_REPO_ID
