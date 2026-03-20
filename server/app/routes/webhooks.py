import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.config import settings
from app.db import async_session
from app.services.webhook_service import EVENT_HANDLERS, verify_signature

logger = logging.getLogger(__name__)

router = APIRouter()


async def _dispatch_event(event_type: str, payload: dict) -> None:
    handlers = EVENT_HANDLERS.get(event_type, [])
    if not handlers:
        logger.info("no handler for event_type=%s", event_type)
        return
    async with async_session() as session:
        for handler in handlers:
            try:
                await handler(payload, session)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("handler failed for event_type=%s", event_type)


_MAX_WEBHOOK_BODY = 25 * 1024 * 1024  # 25 MB


@router.post("/webhooks/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    body = await request.body()

    if len(body) > _MAX_WEBHOOK_BODY:
        return Response(status_code=413)

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, settings.github_webhook_secret):
        return Response(status_code=401)

    if request.headers.get("content-type", "") != "application/json":
        return Response(status_code=415)

    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400)

    event_type = request.headers.get("X-GitHub-Event", "")

    logger.info(
        "webhook received event_type=%s action=%s",
        event_type,
        payload.get("action", ""),
    )

    background_tasks.add_task(_dispatch_event, event_type, payload)
    return Response(status_code=200)
