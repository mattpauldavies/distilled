import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.config import settings
from app.db import async_session
from app.rate_limit import limiter
from app.services.webhook_service import (
    EVENT_HANDLERS,
    record_webhook_outcome,
    record_webhook_received,
    verify_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _dispatch_event(event_type: str, payload: dict, delivery_id: str) -> None:
    handlers = EVENT_HANDLERS.get(event_type, [])
    if not handlers:
        logger.info("no handler for event_type=%s", event_type)
        await record_webhook_outcome(delivery_id, "no_handler", None)
        return
    first_error: str | None = None
    async with async_session() as session:
        for handler in handlers:
            try:
                await handler(payload, session)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.exception("handler failed for event_type=%s", event_type)
                if first_error is None:
                    first_error = f"{type(exc).__name__}: {exc}"
    status = "failed" if first_error else "succeeded"
    await record_webhook_outcome(delivery_id, status, first_error)


_MAX_WEBHOOK_BODY = 25 * 1024 * 1024  # 25 MB


@router.post("/webhooks/github")
@limiter.limit("60/minute")
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    # Pre-check Content-Length before reading body into memory
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_WEBHOOK_BODY:
        return Response(status_code=413)

    body = await request.body()

    if len(body) > _MAX_WEBHOOK_BODY:
        return Response(status_code=413)

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, settings.github_webhook_secret):
        return Response(status_code=401)

    if request.headers.get("content-type", "") != "application/json":
        return Response(status_code=415)

    try:
        payload = json.loads(body)
    except Exception:
        return Response(status_code=400)

    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    if not delivery_id:
        # GitHub always sends X-GitHub-Delivery; missing it means the request is malformed.
        return Response(status_code=400)

    logger.info(
        "webhook_received delivery_id=%s event_type=%s action=%s",
        delivery_id,
        event_type,
        payload.get("action", ""),
    )

    await record_webhook_received(
        delivery_id=delivery_id,
        event_type=event_type,
        action=payload.get("action"),
        payload_bytes=len(body),
    )

    background_tasks.add_task(_dispatch_event, event_type, payload, delivery_id)
    return Response(status_code=200)
