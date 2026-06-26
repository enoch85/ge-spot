"""Regression tests: ApiClient must not log handled HTTP 429 at ERROR level.

A 429 (rate limit) is expected and handled by the retry/fallback path, and
``_track_error_response`` already surfaces it once at WARNING. The per-request
detail should be DEBUG so a rate-limited source shared by many areas does not
flood the log with ERRORs. Other non-200 statuses (e.g. 500) stay ERROR.
"""

import logging

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


async def test_500_still_logged_as_error(caplog):
    """A genuine server error (500) must still be logged at ERROR."""
    client = ApiClient(session=_FakeSession(_FakeResponse(500, body="boom")))

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        result = await client.fetch("https://example.test/x")

    assert result.get("status_code") == 500
    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert any(
        "status 500" in m for m in errors
    ), f"500 should log ERROR, got: {errors}"
