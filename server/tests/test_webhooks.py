import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


def sign_payload(payload: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


SECRET = "test-webhook-secret"


@pytest.fixture
def webhook_client():
    app = create_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


class TestWebhookSignature:
    @patch("app.routes.webhooks.settings")
    async def test_valid_signature_returns_200(self, mock_settings, webhook_client):
        mock_settings.github_webhook_secret = SECRET
        body = json.dumps({"action": "created"}).encode()
        sig = sign_payload(body, SECRET)

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200

    @patch("app.routes.webhooks.settings")
    async def test_invalid_signature_returns_401(self, mock_settings, webhook_client):
        mock_settings.github_webhook_secret = SECRET
        body = json.dumps({"action": "created"}).encode()

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    @patch("app.routes.webhooks.settings")
    async def test_missing_signature_returns_401(self, mock_settings, webhook_client):
        mock_settings.github_webhook_secret = SECRET
        body = json.dumps({"action": "created"}).encode()

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401


class TestWebhookDispatch:
    @patch("app.routes.webhooks._dispatch_event", new_callable=AsyncMock)
    @patch("app.routes.webhooks.settings")
    async def test_dispatches_event_to_background(self, mock_settings, mock_dispatch, webhook_client):
        mock_settings.github_webhook_secret = SECRET
        payload = {"action": "created", "installation": {"id": 1}}
        body = json.dumps(payload).encode()
        sig = sign_payload(body, SECRET)

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200


class TestDispatchEvent:
    @patch("app.routes.webhooks.async_session")
    async def test_calls_registered_handlers(self, mock_session_factory):
        from app.routes.webhooks import _dispatch_event

        handler = AsyncMock()
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.webhooks.EVENT_HANDLERS", {"test_event": [handler]}):
            await _dispatch_event("test_event", {"data": 1})

        handler.assert_awaited_once_with({"data": 1}, mock_session)
        mock_session.commit.assert_awaited_once()

    @patch("app.routes.webhooks.async_session")
    async def test_no_handlers_does_nothing(self, mock_session_factory):
        from app.routes.webhooks import _dispatch_event

        with patch("app.routes.webhooks.EVENT_HANDLERS", {}):
            await _dispatch_event("unknown_event", {})

        mock_session_factory.assert_not_called()

    @patch("app.routes.webhooks.async_session")
    async def test_handler_exception_rolls_back(self, mock_session_factory):
        from app.routes.webhooks import _dispatch_event

        handler = AsyncMock(side_effect=ValueError("boom"))
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.webhooks.EVENT_HANDLERS", {"test_event": [handler]}):
            await _dispatch_event("test_event", {})

        mock_session.rollback.assert_awaited_once()
