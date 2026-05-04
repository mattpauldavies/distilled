import hashlib
import hmac
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from app.db import async_session
from app.models.webhook_event import WebhookEvent

logger = logging.getLogger(__name__)

EVENT_HANDLERS: dict[str, list] = {}

_MAX_ERROR_LEN = 2048


def register_handler(event_type: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a webhook event handler."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        EVENT_HANDLERS.setdefault(event_type, []).append(func)
        return func

    return decorator


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not secret:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


async def record_received(
    delivery_id: str,
    event_type: str,
    action: str | None,
    payload_bytes: int,
) -> None:
    """Insert a webhook_events row in status='received'. Idempotent on delivery_id.

    Opens its own session so the row survives any later rollback in the dispatcher.
    """
    stmt = (
        insert(WebhookEvent)
        .values(
            id=uuid.uuid4(),
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            status="received",
            payload_bytes=payload_bytes,
        )
        .on_conflict_do_nothing(index_elements=["delivery_id"])
    )
    async with async_session() as session:
        await session.execute(stmt)
        await session.commit()


async def record_outcome(delivery_id: str, status: str, error: str | None) -> None:
    """Update a webhook_events row with terminal status, processed_at, and (optional) error.

    No-op if no row matches delivery_id (defensive — shouldn't happen in practice).
    """
    stmt = (
        update(WebhookEvent)
        .where(WebhookEvent.delivery_id == delivery_id)
        .values(
            status=status,
            processed_at=datetime.now(UTC),
            error_message=error[:_MAX_ERROR_LEN] if error else None,
        )
    )
    async with async_session() as session:
        await session.execute(stmt)
        await session.commit()
