import logging
import time

import httpx
import jwt
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from app.config import settings

logger = logging.getLogger(__name__)


class ClerkJWTVerifier:
    """Fetches and caches Clerk JWKS; validates incoming JWTs."""

    def __init__(self) -> None:
        self._jwks_data: dict | None = None
        self._fetched_at: float | None = None
        self._ttl: int = 3600  # 1 hour

    async def get_jwks(self) -> dict:
        now = time.monotonic()
        if self._jwks_data is None or (
            self._fetched_at is not None and now - self._fetched_at > self._ttl
        ):
            async with httpx.AsyncClient() as client:
                resp = await client.get(settings.clerk_jwks_url, timeout=10)
                resp.raise_for_status()
                self._jwks_data = resp.json()
                self._fetched_at = now
        return self._jwks_data  # type: ignore[return-value]

    async def get_user(self, clerk_user_id: str) -> dict:
        """Fetch full user profile from Clerk Backend API."""
        if not settings.clerk_secret_key:
            raise HTTPException(status_code=503, detail="Clerk secret key not configured")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.clerk.com/v1/users/{clerk_user_id}",
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def verify_token(self, token: str) -> dict:
        if not settings.clerk_jwks_url:
            raise HTTPException(status_code=401, detail="Auth not configured")
        try:
            jwks = await self.get_jwks()
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            key = None
            for jwk_key in jwks.get("keys", []):
                if jwk_key.get("kid") == kid:
                    key = RSAAlgorithm.from_jwk(jwk_key)
                    break

            if key is None:
                logger.warning("clerk_jwt: unknown key ID %s", kid)
                raise HTTPException(status_code=401, detail="Unknown signing key")

            claims: dict = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            return claims
        except HTTPException:
            raise
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
