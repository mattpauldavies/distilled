import hashlib
import hmac

import pytest

from app.services.webhook_service import EVENT_HANDLERS, register_handler, verify_signature


def make_signature(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_signature_valid():
    payload = b"test payload"
    secret = "mysecret"
    sig = make_signature(payload, secret)
    assert verify_signature(payload, sig, secret) is True


def test_verify_signature_invalid():
    payload = b"test payload"
    secret = "mysecret"
    assert verify_signature(payload, "sha256=invalidsignature", secret) is False


def test_verify_signature_missing_prefix():
    payload = b"test payload"
    secret = "mysecret"
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_signature(payload, digest, secret) is False


def test_register_handler_registers_correctly():
    event_type = "_test_event_single"
    EVENT_HANDLERS.pop(event_type, None)

    @register_handler(event_type)
    def handler():
        pass

    try:
        assert event_type in EVENT_HANDLERS
        assert handler in EVENT_HANDLERS[event_type]
    finally:
        EVENT_HANDLERS.pop(event_type, None)


def test_register_handler_multiple_handlers_same_event():
    event_type = "_test_event_multi"
    EVENT_HANDLERS.pop(event_type, None)

    @register_handler(event_type)
    def handler_a():
        pass

    @register_handler(event_type)
    def handler_b():
        pass

    try:
        assert len(EVENT_HANDLERS[event_type]) == 2
        assert handler_a in EVENT_HANDLERS[event_type]
        assert handler_b in EVENT_HANDLERS[event_type]
    finally:
        EVENT_HANDLERS.pop(event_type, None)
