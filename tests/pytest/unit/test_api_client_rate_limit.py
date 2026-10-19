"""Handled upstream failures stay quiet; authentication failures remain visible."""

import logging
from unittest.mock import MagicMock

import aiohttp
import pytest

from custom_components.ge_spot.api.base.api_client import ApiClient
from custom_components.ge_spot.api.energy_charts import EnergyChartsAPI
from custom_components.ge_spot.const.network import Network
from custom_components.ge_spot.coordinator.fallback_manager import FallbackManager


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


class _DroppedConnection:
    """Request context whose connection fails before a response arrives."""

    async def __aenter__(self):
        raise aiohttp.ClientConnectionError("Connection reset by peer")

    async def __aexit__(self, *exc):
        return False


class _SequenceSession:
    """Answers each request with the next of the given responses."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests = 0

    def get(self, *args, **kwargs):
        self.requests += 1
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def no_retry_pause(monkeypatch):
    """Keep the pause before a transient retry out of the test run time."""
    monkeypatch.setattr(
        Network.Defaults, "TRANSIENT_RETRY_DELAY_SECONDS", 0, raising=False
    )


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


@pytest.mark.parametrize(
    "failure", [_FakeResponse(503, body="down"), _DroppedConnection()]
)
async def test_transient_failure_is_retried_once(failure):
    """One server error or dropped connection must not cost a source its prices."""
    session = _SequenceSession(failure, _FakeResponse(200, body='{"price": [70]}'))

    result = await ApiClient(session=session).fetch(
        "https://api.energy-charts.info/price"
    )

    assert result == {"price": [70]}
    assert session.requests == 2


@pytest.mark.parametrize("status", [204, 404, 429, 403])
async def test_missing_data_rate_limit_and_auth_are_not_retried(status):
    """Repeating these requests cannot help and would add load."""
    session = _SequenceSession(_FakeResponse(status, body="no"))

    result = await ApiClient(session=session).fetch("https://example.test/prices")

    assert result["status_code"] == status
    assert session.requests == 1


async def test_transient_retry_happens_once():
    """A second failure is returned; the coordinator schedules later attempts."""
    session = _SequenceSession(_FakeResponse(503), _FakeResponse(502))

    result = await ApiClient(session=session).fetch("https://example.test/prices")

    assert result["status_code"] == 502
    assert session.requests == 2


async def test_energy_charts_recovers_from_one_server_error():
    """The only source returns prices after a single 503 instead of failing."""
    session = _SequenceSession(
        _FakeResponse(503, body="Service Unavailable"),
        _FakeResponse(200, body='{"unix_seconds": [1792195200], "price": [70]}'),
    )
    api = EnergyChartsAPI(session=session)
    api.needs_extended_date_range = MagicMock(
        return_value={"need_yesterday": False, "need_tomorrow": False}
    )

    result = await FallbackManager().fetch_with_fallback([api], "SE4", session=session)

    assert result["raw_data"]["today"]["price"] == [70]
    assert session.requests == 2
