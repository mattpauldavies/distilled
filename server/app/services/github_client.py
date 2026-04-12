import time
from datetime import UTC, datetime, timedelta

import httpx
import jwt

from app.config import settings

# Module-level cache so tokens persist across requests (per-process).
_token_cache: dict[int, tuple[str, datetime]] = {}

_TOKEN_EXPIRY_MARGIN = timedelta(seconds=60)


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

    def _generate_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": str(settings.github_app_id),
        }
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
        resp = await self._http.post(
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
        token = await self.get_installation_token(installation_id)
        repos = []
        page = 1
        while True:
            resp = await self._http.get(
                "/installation/repositories",
                params={"per_page": 100, "page": page},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            repos.extend(data["repositories"])
            if len(repos) >= data["total_count"] or len(repos) >= self._MAX_REPOS:
                break
            page += 1
        return repos

    async def list_environments(self, owner: str, repo: str, installation_id: int) -> list[dict]:
        token = await self.get_installation_token(installation_id)
        resp = await self._http.get(
            f"/repos/{owner}/{repo}/environments",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("environments", [])
