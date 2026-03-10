import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)

EVENT_HANDLERS: dict[str, list] = {}


def register_handler(event_type: str):
    """Decorator to register a webhook event handler."""
    def decorator(func):
        EVENT_HANDLERS.setdefault(event_type, []).append(func)
        return func
    return decorator


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
