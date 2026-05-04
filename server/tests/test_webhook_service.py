import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.services.webhook_service import (
    EVENT_HANDLERS,
    record_outcome,
    record_received,
    register_handler,
    verify_signature,
)


def _patch_session() -> tuple[AsyncMock, MagicMock]:
    """Build a mock async_session() factory and the session it yields."""
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_factory


def _compiled_sql(execute_call) -> str:
    stmt = execute_call.args[0]
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


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


def test_verify_signature_rejects_empty_secret():
    payload = b"test payload"
    sig = make_signature(payload, "")
    assert verify_signature(payload, sig, "") is False


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


# --- record_received ---


@pytest.mark.asyncio
async def test_record_received_inserts_row_in_received_status():
    mock_session, mock_factory = _patch_session()

    with patch("app.services.webhook_service.async_session", mock_factory):
        await record_received(
            delivery_id="abc-123",
            event_type="pull_request",
            action="opened",
            payload_bytes=512,
        )

    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
    sql = _compiled_sql(mock_session.execute.call_args)
    assert "INSERT INTO webhook_events" in sql
    assert "'received'" in sql
    assert "'abc-123'" in sql
    assert "'pull_request'" in sql
    assert "'opened'" in sql
    assert "512" in sql


@pytest.mark.asyncio
async def test_record_received_uses_on_conflict_do_nothing_for_dedup():
    mock_session, mock_factory = _patch_session()

    with patch("app.services.webhook_service.async_session", mock_factory):
        await record_received(
            delivery_id="abc-123",
            event_type="pull_request",
            action=None,
            payload_bytes=10,
        )

    sql = _compiled_sql(mock_session.execute.call_args)
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql


@pytest.mark.asyncio
async def test_record_received_handles_none_action():
    mock_session, mock_factory = _patch_session()

    with patch("app.services.webhook_service.async_session", mock_factory):
        await record_received(
            delivery_id="abc-123",
            event_type="ping",
            action=None,
            payload_bytes=5,
        )

    sql = _compiled_sql(mock_session.execute.call_args)
    assert "INSERT INTO webhook_events" in sql
    assert "NULL" in sql  # action column rendered as NULL


# --- record_outcome ---


@pytest.mark.asyncio
async def test_record_outcome_marks_succeeded():
    mock_session, mock_factory = _patch_session()

    with patch("app.services.webhook_service.async_session", mock_factory):
        await record_outcome("abc-123", "succeeded", None)

    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
    sql = _compiled_sql(mock_session.execute.call_args)
    assert "UPDATE webhook_events" in sql
    assert "'succeeded'" in sql
    assert "delivery_id = 'abc-123'" in sql


@pytest.mark.asyncio
async def test_record_outcome_marks_failed_with_error_message():
    mock_session, mock_factory = _patch_session()

    with patch("app.services.webhook_service.async_session", mock_factory):
        await record_outcome("abc-123", "failed", "boom: KeyError 'foo'")

    sql = _compiled_sql(mock_session.execute.call_args)
    assert "'failed'" in sql
    assert "boom: KeyError" in sql


@pytest.mark.asyncio
async def test_record_outcome_truncates_long_error():
    mock_session, mock_factory = _patch_session()
    long_error = "x" * 5000

    with patch("app.services.webhook_service.async_session", mock_factory):
        await record_outcome("abc-123", "failed", long_error)

    # Inspect the bound parameters rather than literal SQL — 2048 x's would be hard to grep.
    stmt = mock_session.execute.call_args.args[0]
    bound_error = stmt.compile().params["error_message"]
    assert len(bound_error) == 2048


@pytest.mark.asyncio
async def test_record_outcome_marks_no_handler():
    mock_session, mock_factory = _patch_session()

    with patch("app.services.webhook_service.async_session", mock_factory):
        await record_outcome("abc-123", "no_handler", None)

    sql = _compiled_sql(mock_session.execute.call_args)
    assert "'no_handler'" in sql
