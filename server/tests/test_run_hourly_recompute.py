import asyncio
from unittest.mock import patch

import httpx
import pytest

from scripts import run_hourly_recompute as sut


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_fetch_targets_calls_enumeration_endpoint():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "targets": [
                    {"tenant_id": "t1", "repo_id": "r1"},
                    {"tenant_id": "t1", "repo_id": "r2"},
                ],
                "count": 2,
            },
        )

    async with httpx.AsyncClient(
        transport=_mock_transport(handler),
        base_url="http://test",
        headers={"Authorization": "Bearer s"},
    ) as client:
        targets = await sut.fetch_targets(client)

    assert len(targets) == 2
    assert calls[0].url.path == "/metrics/recompute-targets"
    assert calls[0].headers["Authorization"] == "Bearer s"


@pytest.mark.asyncio
async def test_recompute_one_returns_true_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/metrics/recompute"
        return httpx.Response(200, json={"status": "success", "error_message": None})

    async with httpx.AsyncClient(transport=_mock_transport(handler), base_url="http://test") as client:
        ok = await sut.recompute_one(client, {"tenant_id": "t1", "repo_id": "r1"})

    assert ok is True


@pytest.mark.asyncio
async def test_recompute_one_retries_once_on_5xx():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, json={"detail": "transient"})
        return httpx.Response(200, json={"status": "success"})

    async with httpx.AsyncClient(transport=_mock_transport(handler), base_url="http://test") as client:
        with patch.object(sut.asyncio, "sleep", new=lambda _s: asyncio.sleep(0)):
            ok = await sut.recompute_one(client, {"tenant_id": "t1", "repo_id": "r1"})

    assert ok is True
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_recompute_one_gives_up_after_one_retry():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=_mock_transport(handler), base_url="http://test") as client:
        with patch.object(sut.asyncio, "sleep", new=lambda _s: asyncio.sleep(0)):
            ok = await sut.recompute_one(client, {"tenant_id": "t1", "repo_id": "r1"})

    assert ok is False
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_run_fans_out_for_every_target(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")
    monkeypatch.setenv("RECOMPUTE_JITTER_MS", "0")
    monkeypatch.setenv("RECOMPUTE_CONCURRENCY", "2")

    call_log: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        call_log.append(request.url.path)
        if request.url.path.endswith("recompute-targets"):
            return httpx.Response(
                200,
                json={
                    "targets": [
                        {"tenant_id": "t1", "repo_id": "r1"},
                        {"tenant_id": "t1", "repo_id": "r2"},
                        {"tenant_id": "t1", "repo_id": "r3"},
                    ],
                    "count": 3,
                },
            )
        return httpx.Response(200, json={"status": "success"})

    def make_client(**kw):
        return httpx.AsyncClient(transport=_mock_transport(handler), **kw)

    with patch.object(sut.httpx, "AsyncClient", make_client):
        summary = await sut.run()

    assert summary.total == 3
    assert summary.succeeded == 3
    assert summary.failed == 0
    assert call_log.count("/metrics/recompute") == 3


def test_main_exits_1_when_env_missing(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    assert sut.main() == 1


def test_main_exits_1_on_enumeration_failure(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    def make_client(**kw):
        return httpx.AsyncClient(transport=_mock_transport(handler), **kw)

    with patch.object(sut.httpx, "AsyncClient", make_client):
        assert sut.main() == 1


def test_main_exits_0_on_partial_per_repo_failure(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")
    monkeypatch.setenv("RECOMPUTE_JITTER_MS", "0")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("recompute-targets"):
            return httpx.Response(
                200,
                json={"targets": [{"tenant_id": "t1", "repo_id": "r1"}], "count": 1},
            )
        return httpx.Response(500)

    def make_client(**kw):
        return httpx.AsyncClient(transport=_mock_transport(handler), **kw)

    with patch.object(sut.httpx, "AsyncClient", make_client), patch.object(
        sut.asyncio, "sleep", new=lambda _s: asyncio.sleep(0)
    ):
        # Per-repo failures are NOT a scheduler-level failure.
        assert sut.main() == 0
