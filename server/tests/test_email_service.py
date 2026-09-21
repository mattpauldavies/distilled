"""Rendering safety and failure reporting for transactional emails.

Workspace names are attacker-controlled free text (any signed-up user owns a
workspace they can rename), so everything interpolated into email HTML must be
escaped — otherwise invites become a phishing vector sent from our domain.

The provider's own explanation for a rejected send must survive the exception:
without it a 403 is indistinguishable from any other 403.
"""

import logging
from unittest.mock import patch

import httpx
import pytest

from app.services.email_service import (
    EmailDeliveryError,
    ResendEmailService,
    _render_invitation_html,
    _render_invitation_text,
    _subject_text,
)

HOSTILE_TENANT = '</h1><a href="https://evil.example/reset">Reset now</a><div style="display:none">'
HOSTILE_INVITER = "<script>alert(1)</script>"


def test_invitation_html_escapes_tenant_and_inviter_names():
    html_out = _render_invitation_html(
        tenant_name=HOSTILE_TENANT,
        inviter_name=HOSTILE_INVITER,
        accept_url="https://app.example.com/invitations/accept?token=tok",
    )
    assert "<script>" not in html_out
    assert '<a href="https://evil.example/reset">' not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
    # The legitimate accept link must survive untouched.
    assert '<a href="https://app.example.com/invitations/accept?token=tok"' in html_out


def test_invitation_html_leaves_plain_names_readable():
    html_out = _render_invitation_html(
        tenant_name="Acme & Co",
        inviter_name="mattd",
        accept_url="https://app.example.com/accept",
    )
    assert "Acme &amp; Co" in html_out
    assert "mattd invited you" in html_out


def test_subject_strips_control_characters():
    subject = _subject_text(tenant_name="Acme\r\nBcc: victim", inviter_name="matt\nd")
    assert "\r" not in subject
    assert "\n" not in subject
    assert "matt d invited you to Acme Bcc: victim on Distilled" == subject


def test_invitation_text_part_is_plain():
    text = _render_invitation_text(
        tenant_name=HOSTILE_TENANT,
        inviter_name="mattd",
        accept_url="https://app.example.com/accept",
    )
    # Plain-text part is inert; it must simply contain the accept URL.
    assert "https://app.example.com/accept" in text


# --- ResendEmailService error reporting ---
#
# Resend answers a rejected send with a JSON body explaining why (unverified
# domain, restricted key, sandbox-only recipient). `raise_for_status` throws
# that body away, which left a production 403 in Sentry with nothing but the
# status code to go on.

_RealAsyncClient = httpx.AsyncClient

RESEND_403_BODY = {
    "statusCode": 403,
    "name": "validation_error",
    "message": "The distilledmetrics.com domain is not verified. Please verify it at https://resend.com/domains",
}


def _patched_async_client_factory(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kw)

    return factory


async def _send_invitation(handler) -> None:
    service = ResendEmailService(api_key="re_secret_key", from_address="hello@distilled.test")
    with patch.object(httpx, "AsyncClient", _patched_async_client_factory(handler)):
        await service.send_invitation(
            to="max@example.com",
            tenant_name="Malted",
            inviter_name="mattd",
            accept_url="https://app.example.com/accept",
        )


def _responder(status_code: int, **kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, **kwargs)

    return handler


async def test_send_surfaces_resend_error_message():
    with pytest.raises(EmailDeliveryError) as exc_info:
        await _send_invitation(_responder(403, json=RESEND_403_BODY))

    message = str(exc_info.value)
    assert "403" in message
    assert "validation_error" in message
    assert "domain is not verified" in message
    assert "re_secret_key" not in message


async def test_send_falls_back_to_body_text_when_not_json():
    with pytest.raises(EmailDeliveryError) as exc_info:
        await _send_invitation(_responder(403, text="<html>Forbidden by edge proxy</html>"))

    assert "Forbidden by edge proxy" in str(exc_info.value)


async def test_send_truncates_a_long_error_body():
    with pytest.raises(EmailDeliveryError) as exc_info:
        await _send_invitation(_responder(500, text="x" * 5000))

    assert len(str(exc_info.value)) < 700


async def test_send_logs_the_resend_error(caplog):
    with caplog.at_level(logging.ERROR, logger="app.services.email_service"):
        with pytest.raises(EmailDeliveryError):
            await _send_invitation(_responder(403, json=RESEND_403_BODY))

    assert "domain is not verified" in caplog.text


async def test_successful_send_posts_the_rendered_email():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "8f1d-…"})

    await _send_invitation(handler)

    assert len(requests) == 1
    assert requests[0].url == httpx.URL("https://api.resend.com/emails")
    assert requests[0].headers["Authorization"] == "Bearer re_secret_key"
