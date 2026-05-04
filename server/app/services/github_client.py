import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level cache so tokens persist across requests (per-process).
_token_cache: dict[int, tuple[str, datetime]] = {}

_TOKEN_EXPIRY_MARGIN = timedelta(seconds=60)

_TRANSIENT_5XX = {502, 503, 504}
_MAX_ATTEMPTS = 4
_MAX_SERVER_WAIT_S = 30.0


class _RetryableStatusError(httpx.HTTPStatusError):
    """Marker subclass — raised internally so tenacity retries on retryable status codes."""


def _is_rate_limited(response: httpx.Response) -> bool:
    """GitHub signals primary rate limits with 429 and secondary with 403 + remaining=0."""
    if response.status_code == 429:
        return True
    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        return True
    return False


def _server_supplied_wait(response: httpx.Response) -> float | None:
    """Extract a wait duration from Retry-After or x-ratelimit-reset, capped at _MAX_SERVER_WAIT_S."""
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), _MAX_SERVER_WAIT_S)
        except ValueError:
            pass  # HTTP-date form is rare from GitHub; fall through to reset header
    reset = response.headers.get("x-ratelimit-reset")
    if reset:
        try:
            delta = float(reset) - time.time()
            return min(max(delta, 0.0), _MAX_SERVER_WAIT_S)
        except ValueError:
            pass
    return None


_exponential_wait = wait_exponential_jitter(initial=1, max=8)


def _compute_wait(retry_state: RetryCallState) -> float:
    """Prefer server-supplied wait on rate-limit responses; otherwise exponential jitter."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, _RetryableStatusError) and _is_rate_limited(exc.response):
        server_wait = _server_supplied_wait(exc.response)
        if server_wait is not None:
            return server_wait
    return _exponential_wait(retry_state)


def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    status = getattr(getattr(exc, "response", None), "status_code", None)
    logger.warning(
        "github_retry attempt=%s status=%s wait_s=%s error=%s",
        retry_state.attempt_number,
        status,
        round(retry_state.next_action.sleep, 2) if retry_state.next_action else None,
        type(exc).__name__ if exc else None,
    )


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _authed_request(self, installation_id: int, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Issue an installation-authenticated request; on 401, evict the cached token and retry once."""
        headers = {**kwargs.pop("headers", {})}
        token = await self.get_installation_token(installation_id)
        headers["Authorization"] = f"Bearer {token}"
        response = await self._request_with_retry(method, path, headers=headers, **kwargs)
        if response.status_code == 401:
            logger.info("installation_token_evicted installation_id=%s", installation_id)
            _token_cache.pop(installation_id, None)
            token = await self.get_installation_token(installation_id)
            headers["Authorization"] = f"Bearer {token}"
            response = await self._request_with_retry(method, path, headers=headers, **kwargs)
        return response

    async def _request_with_retry(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Issue an HTTP request with bounded retry on transient failures.

        Retried on: httpx.TransportError, httpx.ReadTimeout, and HTTP 429/502/503/504.
        Non-retryable non-2xx responses are returned to the caller (e.g. 404 in list_environments).
        """
        retryable_excs = (httpx.TransportError, httpx.ReadTimeout, _RetryableStatusError)
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(_MAX_ATTEMPTS),
            wait=_compute_wait,
            retry=retry_if_exception_type(retryable_excs),
            reraise=True,
            before_sleep=_log_retry,
        ):
            with attempt:
                response = await self._http.request(method, path, **kwargs)
                if response.status_code in _TRANSIENT_5XX or _is_rate_limited(response):
                    raise _RetryableStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                return response
        raise RuntimeError("unreachable")  # for type checker; tenacity always returns or raises

    def _generate_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": str(settings.github_app_id),
        }
        if settings.github_private_key:
            private_key = settings.github_private_key.encode()
        else:
            with open(settings.github_private_key_path, "rb") as f:
                private_key = f.read()
        return jwt.encode(payload, private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        cached = _token_cache.get(installation_id)
        if cached:
            token, expires_at = cached
            if datetime.now(UTC) < expires_at - _TOKEN_EXPIRY_MARGIN:
                return token

        token_jwt = self._generate_jwt()
        resp = await self._request_with_retry(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {token_jwt}"},
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["token"]
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        _token_cache[installation_id] = (token, expires_at)
        return token

    _MAX_REPOS = 10_000

    async def list_repos(self, installation_id: int) -> list[dict]:
        repos = []
        page = 1
        while True:
            resp = await self._authed_request(
                installation_id,
                "GET",
                "/installation/repositories",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            data = resp.json()
            repos.extend(data["repositories"])
            if len(repos) >= data["total_count"] or len(repos) >= self._MAX_REPOS:
                break
            page += 1
        return repos

    async def list_environments(self, owner: str, repo: str, installation_id: int) -> list[dict]:
        resp = await self._authed_request(
            installation_id,
            "GET",
            f"/repos/{owner}/{repo}/environments",
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("environments", [])
