"""Handled upstream failures stay quiet; authentication failures remain visible."""

import logging
import pytest

from custom_components.ge_spot.api.base.api_client import ApiClient


class _FakeResponse:
    """Minimal async-context-manager stand-in for an aiohttp response."""

    def __init__(self, status, body="", content_type="application/json"):
        self.status = status
        self._body = body
        self.headers = {"Content-Type": content_type}

    async def text(self, encoding=None):
        return self._body

    async def json(self):
        import json

        return json.loads(self._body or "{}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, response):
        self._response = response

    def get(self, *args, **kwargs):
        # aiohttp's session.get(...) is used as an async context manager and is
        # not awaited, so return the context manager directly.
        return self._response


async def test_429_not_logged_as_error(caplog):
    """A 429 response returns the error dict but logs no ERROR record."""
    client = ApiClient(session=_FakeSession(_FakeResponse(429, body="rate limited")))

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        result = await client.fetch("https://api.energy-charts.info/price")

    assert result.get("error") is True
    assert result.get("status_code") == 429
    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert errors == [], f"429 must not log ERROR, got: {errors}"


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_actionable_failure_logged_as_error(caplog, status):
    """Authentication and malformed requests require user/developer intervention."""
    client = ApiClient(session=_FakeSession(_FakeResponse(status, body="denied")))

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        result = await client.fetch("https://example.test/x")

    assert result.get("status_code") == status
    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert any(f"status {status}" in m for m in errors)


async def test_503_not_logged_as_error(caplog):
    """A transient 503 (upstream outage) returns the error dict, no ERROR record."""
    client = ApiClient(
        session=_FakeSession(_FakeResponse(503, body="<html>service down</html>"))
    )

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        result = await client.fetch("https://web-api.tp.entsoe.eu/api")

    assert result.get("error") is True
    assert result.get("status_code") == 503
    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert errors == [], f"503 must not log ERROR, got: {errors}"


@pytest.mark.parametrize("status", [204, 404, 429, 500, 502, 503, 504])
async def test_transient_failures_are_debug_across_clients(caplog, status):
    """A new client per fetch must not restart a warning flood."""

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        for _ in range(2):
            client = ApiClient(session=_FakeSession(_FakeResponse(status)))
            await client.fetch("https://example.test/prices")
    assert caplog.records
    assert all(record.levelno < logging.WARNING for record in caplog.records)
