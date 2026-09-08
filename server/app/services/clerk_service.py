import logging
import time
from typing import cast

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
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
        if self._jwks_data is None or (self._fetched_at is not None and now - self._fetched_at > self._ttl):
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

    async def get_user_emails(self, clerk_user_id: str) -> list[str]:
        """Return verified email addresses for a Clerk user, lower-cased.

        Used to match a signed-in user against pending invitations targeted
        at their email — the GitHub-only sign-in path means we don't see
        the user's email until we ask Clerk for it.
        """
        try:
            profile = await self.get_user(clerk_user_id)
        except HTTPException:
            return []
        emails: list[str] = []
        for entry in profile.get("email_addresses", []) or []:
            verification = (entry.get("verification") or {}).get("status")
            if verification != "verified":
                continue
            address = entry.get("email_address")
            if address:
                emails.append(address.lower())
        return emails

    def _find_key(self, jwks: dict, kid: str) -> RSAPublicKey | None:
        for jwk_key in jwks.get("keys", []):
            if jwk_key.get("kid") == kid:
                return cast(RSAPublicKey, RSAAlgorithm.from_jwk(jwk_key))
        return None

    async def verify_token(self, token: str) -> dict:
        if not settings.clerk_jwks_url:
            raise HTTPException(status_code=401, detail="Auth not configured")
        try:
            jwks = await self.get_jwks()
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            key = self._find_key(jwks, kid) if kid else None

            # On kid miss, force a JWKS refresh and retry once (handles key rotation)
            if key is None and kid:
                self._jwks_data = None
                jwks = await self.get_jwks()
                key = self._find_key(jwks, kid)

            if key is None:
                logger.warning("clerk_jwt: token presented with unknown signing key")
                raise HTTPException(status_code=401, detail="Unknown signing key")

            claims: dict = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=settings.clerk_expected_audience or None,
                issuer=settings.clerk_issuer or None,
                options={"verify_aud": False} if not settings.clerk_expected_audience else None,
            )
            return claims
        except HTTPException:
            raise
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="Token expired") from exc
        except jwt.InvalidTokenError as exc:
            logger.warning("clerk_jwt: invalid token: %s", exc)
            raise HTTPException(status_code=401, detail="Invalid token") from exc
