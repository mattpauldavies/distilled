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
    @patch("app.routes.webhooks.record_received", new_callable=AsyncMock)
    @patch("app.routes.webhooks.settings")
    async def test_valid_signature_returns_200(self, mock_settings, mock_record, webhook_client):
        mock_settings.github_webhook_secret = SECRET
        body = json.dumps({"action": "created"}).encode()
        sig = sign_payload(body, SECRET)

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "delivery-1",
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
    @patch("app.routes.webhooks.record_received", new_callable=AsyncMock)
    @patch("app.routes.webhooks._dispatch_event", new_callable=AsyncMock)
    @patch("app.routes.webhooks.settings")
    async def test_dispatches_event_to_background(
        self, mock_settings, mock_dispatch, mock_record, webhook_client
    ):
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
                "X-GitHub-Delivery": "delivery-abc",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200


class TestWebhookEventRecording:
    @patch("app.routes.webhooks.record_received", new_callable=AsyncMock)
    @patch("app.routes.webhooks._dispatch_event", new_callable=AsyncMock)
    @patch("app.routes.webhooks.settings")
    async def test_received_recorded_before_dispatch_scheduling(
        self, mock_settings, mock_dispatch, mock_record, webhook_client
    ):
        mock_settings.github_webhook_secret = SECRET
        payload = {"action": "opened", "pull_request": {"id": 7}}
        body = json.dumps(payload).encode()
        sig = sign_payload(body, SECRET)

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-xyz",
                "Content-Type": "application/json",
            },
        )

        assert resp.status_code == 200
        mock_record.assert_awaited_once_with(
            delivery_id="delivery-xyz",
            event_type="pull_request",
            action="opened",
            payload_bytes=len(body),
        )

    @patch("app.routes.webhooks.record_received", new_callable=AsyncMock)
    @patch("app.routes.webhooks._dispatch_event", new_callable=AsyncMock)
    @patch("app.routes.webhooks.settings")
    async def test_missing_delivery_id_returns_400(
        self, mock_settings, mock_dispatch, mock_record, webhook_client
    ):
        mock_settings.github_webhook_secret = SECRET
        body = json.dumps({"action": "opened"}).encode()
        sig = sign_payload(body, SECRET)

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
                # No X-GitHub-Delivery header
            },
        )

        assert resp.status_code == 400
        mock_record.assert_not_awaited()

    @patch("app.routes.webhooks.record_received", new_callable=AsyncMock)
    @patch("app.routes.webhooks._dispatch_event", new_callable=AsyncMock)
    @patch("app.routes.webhooks.settings")
    async def test_rejected_webhook_does_not_record(
        self, mock_settings, mock_dispatch, mock_record, webhook_client
    ):
        mock_settings.github_webhook_secret = SECRET
        body = json.dumps({"action": "opened"}).encode()

        resp = await webhook_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-xyz",
                "Content-Type": "application/json",
            },
        )

        assert resp.status_code == 401
        mock_record.assert_not_awaited()


class TestDispatchEvent:
    @patch("app.routes.webhooks.record_outcome", new_callable=AsyncMock)
    @patch("app.routes.webhooks.async_session")
    async def test_calls_registered_handlers(self, mock_session_factory, mock_record_outcome):
        from app.routes.webhooks import _dispatch_event

        handler = AsyncMock()
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.webhooks.EVENT_HANDLERS", {"test_event": [handler]}):
            await _dispatch_event("test_event", {"data": 1}, "delivery-1")

        handler.assert_awaited_once_with({"data": 1}, mock_session)
        mock_session.commit.assert_awaited_once()
        mock_record_outcome.assert_awaited_once_with("delivery-1", "succeeded", None)

    @patch("app.routes.webhooks.record_outcome", new_callable=AsyncMock)
    @patch("app.routes.webhooks.async_session")
    async def test_no_handlers_records_no_handler(self, mock_session_factory, mock_record_outcome):
        from app.routes.webhooks import _dispatch_event

        with patch("app.routes.webhooks.EVENT_HANDLERS", {}):
            await _dispatch_event("unknown_event", {}, "delivery-2")

        mock_session_factory.assert_not_called()
        mock_record_outcome.assert_awaited_once_with("delivery-2", "no_handler", None)

    @patch("app.routes.webhooks.record_outcome", new_callable=AsyncMock)
    @patch("app.routes.webhooks.async_session")
    async def test_handler_exception_rolls_back_and_records_failed(
        self, mock_session_factory, mock_record_outcome
    ):
        from app.routes.webhooks import _dispatch_event

        handler = AsyncMock(side_effect=ValueError("boom"))
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.webhooks.EVENT_HANDLERS", {"test_event": [handler]}):
            await _dispatch_event("test_event", {}, "delivery-3")

        mock_session.rollback.assert_awaited_once()
        mock_record_outcome.assert_awaited_once()
        call = mock_record_outcome.call_args
        assert call.args[0] == "delivery-3"
        assert call.args[1] == "failed"
        assert "boom" in call.args[2]

    @patch("app.routes.webhooks.record_outcome", new_callable=AsyncMock)
    @patch("app.routes.webhooks.async_session")
    async def test_first_handler_failure_recorded_when_later_handler_succeeds(
        self, mock_session_factory, mock_record_outcome
    ):
        """If multiple handlers run and any fails, the outcome is 'failed' with the first error."""
        from app.routes.webhooks import _dispatch_event

        failing = AsyncMock(side_effect=ValueError("first failure"))
        passing = AsyncMock()
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.webhooks.EVENT_HANDLERS", {"test_event": [failing, passing]}):
            await _dispatch_event("test_event", {}, "delivery-4")

        # Both handlers ran (existing behaviour).
        failing.assert_awaited_once()
        passing.assert_awaited_once()
        # Outcome reflects the first (and only) failure.
        call = mock_record_outcome.call_args
        assert call.args[1] == "failed"
        assert "first failure" in call.args[2]
