from unittest.mock import patch

import httpx
import pytest

from scripts import expire_invitations as sut

_RealClient = httpx.Client


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def _patched_client_factory(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _RealClient(transport=_mock_transport(handler), **kw)

    return factory


def test_expire_calls_janitor_endpoint_with_bearer():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"expired": 3})

    with httpx.Client(
        transport=_mock_transport(handler),
        base_url="http://test",
        headers={"Authorization": "Bearer s"},
    ) as client:
        expired = sut.expire(client)

    assert expired == 3
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/internal/invitations/expire"
    assert calls[0].headers["Authorization"] == "Bearer s"


def test_expire_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid authorization"})

    with httpx.Client(transport=_mock_transport(handler), base_url="http://test") as client:
        with pytest.raises(httpx.HTTPStatusError):
            sut.expire(client)


def test_main_exits_1_when_env_missing(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    assert sut.main() == 1


def test_main_exits_1_on_error_status(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with patch.object(sut.httpx, "Client", _patched_client_factory(handler)):
        assert sut.main() == 1


def test_main_exits_1_when_unreachable(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with patch.object(sut.httpx, "Client", _patched_client_factory(handler)):
        assert sut.main() == 1


def test_main_exits_0_on_success(monkeypatch, capsys):
    monkeypatch.setenv("API_BASE_URL", "http://test")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"expired": 2})

    with patch.object(sut.httpx, "Client", _patched_client_factory(handler)):
        assert sut.main() == 0

    assert "expired=2" in capsys.readouterr().out
