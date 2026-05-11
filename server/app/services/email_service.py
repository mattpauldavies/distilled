"""Email delivery for transactional product emails.

Decoupled from Clerk so we can extend later (digest emails, billing receipts)
without rewiring identity. The interface is intentionally narrow: each method
maps to one product-significant message; we don't expose a generic send.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService(Protocol):
    async def send_invitation(
        self,
        *,
        to: str,
        tenant_name: str,
        inviter_name: str,
        accept_url: str,
    ) -> None: ...


def _render_invitation_html(*, tenant_name: str, inviter_name: str, accept_url: str) -> str:
    return f"""<!doctype html>
<html>
  <body style="background:#0b0c0f;color:#e6e6e6;font-family:system-ui,sans-serif;padding:32px;">
    <div style="max-width:480px;margin:0 auto;">
      <h1 style="font-size:18px;font-weight:600;margin:0 0 16px;">
        {inviter_name} invited you to {tenant_name} on Distilled
      </h1>
      <p style="font-size:14px;color:#a8a8a8;line-height:1.5;margin:0 0 24px;">
        Distilled gives engineering leaders a calm, trustworthy view of
        delivery health. Accept the invite to see {tenant_name}'s metrics.
      </p>
      <a href="{accept_url}"
         style="display:inline-block;background:#fff;color:#0b0c0f;
                padding:10px 16px;border-radius:6px;font-weight:600;
                font-size:14px;text-decoration:none;">
        Accept invitation
      </a>
      <p style="font-size:12px;color:#6b6b6b;margin:24px 0 0;">
        If you weren't expecting this, you can ignore this email.
      </p>
    </div>
  </body>
</html>"""


def _render_invitation_text(*, tenant_name: str, inviter_name: str, accept_url: str) -> str:
    return (
        f"{inviter_name} invited you to {tenant_name} on Distilled.\n\n"
        f"Accept here: {accept_url}\n\n"
        "If you weren't expecting this, you can ignore this email."
    )


class LoggingEmailService:
    """Dev/test implementation. Logs the rendered email and accept URL.

    Useful for local development: the accept URL prints in `make server` logs
    and you can paste it into a browser to redeem an invitation without
    needing a real inbox.
    """

    async def send_invitation(
        self,
        *,
        to: str,
        tenant_name: str,
        inviter_name: str,
        accept_url: str,
    ) -> None:
        logger.info(
            "email[log]: invitation to=%s tenant=%s inviter=%s url=%s",
            to,
            tenant_name,
            inviter_name,
            accept_url,
        )


class ResendEmailService:
    """Production implementation using Resend's HTTP API."""

    _ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, *, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from = from_address

    async def send_invitation(
        self,
        *,
        to: str,
        tenant_name: str,
        inviter_name: str,
        accept_url: str,
    ) -> None:
        subject = f"{inviter_name} invited you to {tenant_name} on Distilled"
        payload = {
            "from": self._from,
            "to": [to],
            "subject": subject,
            "html": _render_invitation_html(
                tenant_name=tenant_name,
                inviter_name=inviter_name,
                accept_url=accept_url,
            ),
            "text": _render_invitation_text(
                tenant_name=tenant_name,
                inviter_name=inviter_name,
                accept_url=accept_url,
            ),
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            resp.raise_for_status()


def build_email_service() -> EmailService:
    """Construct the configured email service. Called at startup and per route.

    Lightweight construction — no I/O — so building per call is fine.
    """
    if settings.email_provider == "resend":
        if not settings.resend_api_key or not settings.email_from:
            logger.warning(
                "email_service: provider=resend but resend_api_key/email_from missing; falling back to logging"
            )
            return LoggingEmailService()
        return ResendEmailService(
            api_key=settings.resend_api_key,
            from_address=settings.email_from,
        )
    return LoggingEmailService()
