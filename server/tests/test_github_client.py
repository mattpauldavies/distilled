from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.github_client import GitHubClient, _token_cache


def _make_response(status_code: int, json_data: dict | None = None, headers: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    resp.request = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=resp.request, response=resp
        )
    return resp


def _make_mock_http(request_returns=None, request_side_effect=None) -> MagicMock:
    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()
    if request_side_effect is not None:
        mock_client.request = AsyncMock(side_effect=request_side_effect)
    elif request_returns is not None:
        mock_client.request = AsyncMock(return_value=request_returns)
    return mock_client


@pytest.fixture(autouse=True)
def sleep_mock():
    """tenacity calls asyncio.sleep between retries — mock it so tests don't wait
    and so individual tests can inspect call durations."""
    with patch("asyncio.sleep", new=AsyncMock()) as m:
        yield m


@pytest.fixture(autouse=True)
def _clear_token_cache():
    _token_cache.clear()
    yield
    _token_cache.clear()


def _future_iso() -> str:
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")


# --- _request_with_retry: basic retry behaviour ---


async def test_request_succeeds_first_try():
    mock_http = _make_mock_http(request_returns=_make_response(200, {"ok": True}))

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 200
    assert mock_http.request.call_count == 1


async def test_request_retries_on_503_then_succeeds():
    responses = [_make_response(503), _make_response(200)]
    mock_http = _make_mock_http(request_side_effect=responses)

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 200
    assert mock_http.request.call_count == 2


async def test_request_retries_on_transport_error_then_succeeds():
    side_effect = [httpx.ConnectError("boom"), _make_response(200)]
    mock_http = _make_mock_http(request_side_effect=side_effect)

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 200
    assert mock_http.request.call_count == 2


async def test_request_retries_on_read_timeout_then_succeeds():
    side_effect = [httpx.ReadTimeout("slow"), _make_response(200)]
    mock_http = _make_mock_http(request_side_effect=side_effect)

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 200
    assert mock_http.request.call_count == 2


async def test_request_does_not_retry_on_404():
    """404 is non-retryable — caller decides what to do (e.g. list_environments treats it as empty)."""
    mock_http = _make_mock_http(request_returns=_make_response(404))

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 404
    assert mock_http.request.call_count == 1


async def test_request_exhausts_retries_and_raises_http_status_error():
    responses = [_make_response(503)] * 4
    mock_http = _make_mock_http(request_side_effect=responses)

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client._request_with_retry("GET", "/foo")

    assert exc_info.value.response.status_code == 503
    assert mock_http.request.call_count == 4


# --- _request_with_retry: server-supplied wait honouring ---


def _max_sleep_duration(sleep_mock: AsyncMock) -> float:
    """Largest single sleep duration tenacity asked for during the test."""
    return max((call.args[0] for call in sleep_mock.call_args_list if call.args), default=0.0)


async def test_request_honours_retry_after_on_429(sleep_mock):
    responses = [
        _make_response(429, headers={"retry-after": "2"}),
        _make_response(200),
    ]
    mock_http = _make_mock_http(request_side_effect=responses)

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 200
    assert mock_http.request.call_count == 2
    assert _max_sleep_duration(sleep_mock) >= 2.0


async def test_request_caps_retry_after_at_30s(sleep_mock):
    responses = [
        _make_response(429, headers={"retry-after": "120"}),
        _make_response(200),
    ]
    mock_http = _make_mock_http(request_side_effect=responses)

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 200
    # Retry-After: 120 is capped at 30s.
    assert _max_sleep_duration(sleep_mock) == 30.0


async def test_request_honours_x_ratelimit_reset_on_403(sleep_mock):
    """403 with x-ratelimit-remaining: 0 is GitHub's secondary rate limit signal."""
    import time as time_mod

    reset_at = int(time_mod.time()) + 5
    responses = [
        _make_response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset_at)},
        ),
        _make_response(200),
    ]
    mock_http = _make_mock_http(request_side_effect=responses)

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 200
    assert mock_http.request.call_count == 2
    # Should have waited approximately 5 seconds (reset_at - now), with small slack.
    assert 4.0 <= _max_sleep_duration(sleep_mock) <= 6.0


async def test_request_does_not_retry_on_403_without_rate_limit_header():
    """403 without the rate-limit header is a permission failure — surface it, don't retry."""
    mock_http = _make_mock_http(request_returns=_make_response(403))

    with patch("httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient()
        resp = await client._request_with_retry("GET", "/foo")

    assert resp.status_code == 403
    assert mock_http.request.call_count == 1


# --- list_environments / list_repos: token-refresh-on-401 ---


async def test_401_evicts_token_cache_and_retries_once():
    installation_id = 999
    _token_cache[installation_id] = ("stale-token", datetime.now(UTC) + timedelta(hours=1))

    side_effect = [
        _make_response(401),  # initial GET with stale token
        _make_response(201, {"token": "fresh-token", "expires_at": _future_iso()}),  # token refresh POST
        _make_response(200, {"environments": [{"name": "production"}]}),  # retry GET with fresh token
    ]
    mock_http = _make_mock_http(request_side_effect=side_effect)

    with (
        patch("httpx.AsyncClient", return_value=mock_http),
        patch.object(GitHubClient, "_generate_jwt", return_value="jwt"),
    ):
        client = GitHubClient()
        envs = await client.list_environments("org", "repo", installation_id)

    assert envs == [{"name": "production"}]
    assert mock_http.request.call_count == 3  # GET, POST(token), GET
    assert _token_cache[installation_id][0] == "fresh-token"


async def test_terminal_401_after_eviction_surfaces():
    installation_id = 999
    _token_cache[installation_id] = ("stale-token", datetime.now(UTC) + timedelta(hours=1))

    side_effect = [
        _make_response(401),  # initial GET
        _make_response(201, {"token": "fresh-token", "expires_at": _future_iso()}),  # refresh POST
        _make_response(401),  # retry GET still 401 — terminal
    ]
    mock_http = _make_mock_http(request_side_effect=side_effect)

    with (
        patch("httpx.AsyncClient", return_value=mock_http),
        patch.object(GitHubClient, "_generate_jwt", return_value="jwt"),
    ):
        client = GitHubClient()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.list_environments("org", "repo", installation_id)

    assert exc_info.value.response.status_code == 401
    assert mock_http.request.call_count == 3  # No further loop after second 401


async def test_200_does_not_evict_token_cache():
    """Sanity check: a successful call must not perturb the cache."""
    installation_id = 999
    _token_cache[installation_id] = ("good-token", datetime.now(UTC) + timedelta(hours=1))

    mock_http = _make_mock_http(request_returns=_make_response(200, {"environments": []}))

    with (
        patch("httpx.AsyncClient", return_value=mock_http),
        patch.object(GitHubClient, "_generate_jwt", return_value="jwt"),
    ):
        client = GitHubClient()
        envs = await client.list_environments("org", "repo", installation_id)

    assert envs == []
    assert mock_http.request.call_count == 1  # just the GET, no token refresh
    assert _token_cache[installation_id][0] == "good-token"
