import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.clerk_service import ClerkJWTVerifier


def make_mock_http_client(jwks_data: dict) -> MagicMock:
    """Build a mock httpx.AsyncClient that returns the given JWKS JSON."""
    mock_response = MagicMock()
    mock_response.json.return_value = jwks_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_get_jwks_fetches_on_first_call():
    """JWKS is fetched from the remote URL on the first call."""
    verifier = ClerkJWTVerifier()
    test_jwks = {"keys": [{"kid": "key-1", "kty": "RSA"}]}
    mock_client = make_mock_http_client(test_jwks)

    with patch("app.services.clerk_service.settings") as mock_settings, patch(
        "httpx.AsyncClient", return_value=mock_client
    ):
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        result = await verifier.get_jwks()

    assert result == test_jwks
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_jwks_caches_result():
    """JWKS is only fetched once within the TTL; second call uses cached value."""
    verifier = ClerkJWTVerifier()
    test_jwks = {"keys": [{"kid": "key-1", "kty": "RSA"}]}
    mock_client = make_mock_http_client(test_jwks)

    with patch("app.services.clerk_service.settings") as mock_settings, patch(
        "httpx.AsyncClient", return_value=mock_client
    ):
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        result1 = await verifier.get_jwks()
        result2 = await verifier.get_jwks()

    assert result1 == test_jwks
    assert result2 == test_jwks
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_jwks_refetches_after_ttl():
    """JWKS is re-fetched after the TTL expires."""
    verifier = ClerkJWTVerifier()
    verifier._ttl = 1  # 1 second TTL for test
    test_jwks = {"keys": []}
    mock_client = make_mock_http_client(test_jwks)

    with patch("app.services.clerk_service.settings") as mock_settings, patch(
        "httpx.AsyncClient", return_value=mock_client
    ):
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        await verifier.get_jwks()
        # Simulate TTL expiry
        verifier._fetched_at = time.monotonic() - 2
        await verifier.get_jwks()

    assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_verify_token_raises_401_when_jwks_url_not_configured():
    """verify_token raises 401 HTTPException when CLERK_JWKS_URL is not set."""
    from fastapi import HTTPException

    verifier = ClerkJWTVerifier()

    with patch("app.services.clerk_service.settings") as mock_settings:
        mock_settings.clerk_jwks_url = ""
        with pytest.raises(HTTPException) as exc_info:
            await verifier.verify_token("some.jwt.token")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_token_raises_401_for_invalid_token():
    """verify_token raises 401 HTTPException for a malformed JWT."""
    from fastapi import HTTPException

    verifier = ClerkJWTVerifier()
    test_jwks = {"keys": []}
    mock_client = make_mock_http_client(test_jwks)

    with patch("app.services.clerk_service.settings") as mock_settings, patch(
        "httpx.AsyncClient", return_value=mock_client
    ):
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        with pytest.raises(HTTPException) as exc_info:
            await verifier.verify_token("not.a.valid.jwt")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_token_raises_401_for_unknown_kid():
    """verify_token raises 401 when the JWT key ID is not found in JWKS."""
    import jwt as pyjwt
    from fastapi import HTTPException

    verifier = ClerkJWTVerifier()
    test_jwks = {"keys": [{"kid": "different-key", "kty": "RSA"}]}
    mock_client = make_mock_http_client(test_jwks)

    # Create a token with a different kid (decode without verification to fake the header)
    fake_token = pyjwt.encode({"sub": "user_123"}, "secret", algorithm="HS256", headers={"kid": "unknown-kid"})

    with patch("app.services.clerk_service.settings") as mock_settings, patch(
        "httpx.AsyncClient", return_value=mock_client
    ):
        mock_settings.clerk_jwks_url = "https://test.clerk.accounts.dev/.well-known/jwks.json"
        with pytest.raises(HTTPException) as exc_info:
            await verifier.verify_token(fake_token)

    assert exc_info.value.status_code == 401
    assert "Unknown signing key" in exc_info.value.detail
