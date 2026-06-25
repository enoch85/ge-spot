#!/usr/bin/env python3
"""Tests for the ExchangeService functionality.

These tests verify real-world behavior of the ExchangeService to ensure:
1. Accurate currency conversion using both live and historical rates
2. Proper error handling for API failures and network issues
3. Effective caching with appropriate expiry times
4. Graceful fallback to default rates when necessary
5. Correct handling of various currency pairs and formats

If any test fails, investigate and fix the core implementation rather than adapting tests.
"""

import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, timezone
import pytest
import json
from aiohttp import ClientError, ClientResponseError, ClientSession, ClientResponse
import xml.etree.ElementTree as ET
import time

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.utils.exchange_service import (
    ExchangeRateService,
    ExchangeRateFetchError,
    get_exchange_service,
    EXCHANGE_RATE_CACHE_FILENAME,
)
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.defaults import Defaults
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.const.api import ECB
from custom_components.ge_spot.const.network import Network

# Mock exchange rate data for ECB XML format
MOCK_ECB_XML_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
    <gesmes:subject>Reference rates</gesmes:subject>
    <gesmes:Sender>
        <gesmes:name>European Central Bank</gesmes:name>
    </gesmes:Sender>
    <Cube>
        <Cube time="2023-04-27">
            <Cube currency="USD" rate="1.0828"/>
            <Cube currency="SEK" rate="11.1430"/>
            <Cube currency="NOK" rate="11.5480"/>
            <Cube currency="DKK" rate="7.4530"/>
            <Cube currency="GBP" rate="0.8661"/>
            <Cube currency="AUD" rate="1.6412"/>
        </Cube>
    </Cube>
</gesmes:Envelope>
"""

# Invalid/malformed response
MOCK_INVALID_XML_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
    <gesmes:subject>Reference rates</gesmes:subject>
    <gesmes:Sender>
        <gesmes:name>European Central Bank</gesmes:name>
    </gesmes:Sender>
    <!-- Missing Cube elements -->
</gesmes:Envelope>
"""


@pytest.fixture
async def exchange_service():
    """Create an instance of ExchangeRateService for testing."""
    # Create mock session
    mock_session = MagicMock(spec=ClientSession)
    mock_session.closed = False
    mock_session.close = AsyncMock()

    # Create service instance with a temporary cache file to avoid using real cached data
    service = ExchangeRateService(
        session=mock_session, cache_file="/tmp/test_exchange_rates.json"
    )

    # Reset internal state
    service.rates = {}
    service.last_update = 0

    yield service

    # Clean up
    if not mock_session.closed:
        await service.close()

    # Clean up test cache file
    if os.path.exists("/tmp/test_exchange_rates.json"):
        os.remove("/tmp/test_exchange_rates.json")


@pytest.mark.asyncio
async def test_convert_currency_success(exchange_service):
    """Test successful currency conversion with live rates."""
    # Arrange - Use patching to bypass the actual API call
    mock_rates = {
        Currency.EUR: 1.0,
        Currency.CENTS: 100.0,
        "USD": 1.0828,
        "SEK": 11.1430,
        "NOK": 11.5480,
    }

    # Directly patch the _fetch_ecb_rates method
    with patch.object(
        exchange_service, "_fetch_ecb_rates", AsyncMock(return_value=mock_rates)
    ):
        # Act - Force a rates refresh
        await exchange_service.get_rates(force_refresh=True)

        # Verify rates were loaded correctly
        assert exchange_service.rates[Currency.EUR] == 1.0
        assert exchange_service.rates["SEK"] == 11.1430

        # Now test conversion
        amount = 100.0
        from_currency = Currency.EUR
        to_currency = "SEK"
        result = await exchange_service.convert(amount, from_currency, to_currency)

        # Assert
        assert result is not None, "Conversion rate should not be None"
        expected_rate = 11.1430  # SEK rate from mock data
        expected_amount = amount * expected_rate
        assert (
            abs(result - expected_amount) < 0.01
        ), f"Expected conversion of 100 EUR → SEK to be ~{expected_amount}, got {result}"


@pytest.mark.asyncio
async def test_convert_currency_caching(exchange_service):
    """Test that rates are cached and not fetched for every conversion."""
    # Setup initial rates
    mock_rates = {
        Currency.EUR: 1.0,
        Currency.CENTS: 100.0,
        "USD": 1.0828,
        "SEK": 11.1430,
        "NOK": 11.5480,
    }

    # Use patching with a spy to track calls
    with patch.object(
        exchange_service, "_fetch_ecb_rates", AsyncMock(return_value=mock_rates)
    ) as mock_fetch:
        # Act - First call to get rates
        await exchange_service.get_rates(force_refresh=True)

        # Assert the fetch was called once
        mock_fetch.assert_called_once()
        mock_fetch.reset_mock()

        # Act - Second conversion should use cached rates without fetching
        await exchange_service.convert(
            amount=50.0, from_currency=Currency.EUR, to_currency="NOK"
        )

        # Assert fetch wasn't called again
        mock_fetch.assert_not_called()

        # Force refresh with old timestamp
        exchange_service.last_update = 0

        # Act - Third conversion should refresh rates
        await exchange_service.get_rates(force_refresh=True)

        # Assert fetch was called again
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_convert_currency_api_error(exchange_service):
    """Test handling of API errors with appropriate fallback."""
    # Pre-populate fresh rates (1h old) to test fallback to existing rates
    exchange_service.rates = {Currency.EUR: 1.0, Currency.SEK: 10.0, Currency.USD: 1.1}
    exchange_service.last_update = time.time() - 3600  # 1 hour ago (fresh)

    # Simulate API error by having _fetch_ecb_rates return None
    with patch.object(
        exchange_service, "_fetch_ecb_rates", AsyncMock(return_value=None)
    ):
        # Act - Should keep existing (still-fresh) rates when fetch fails
        rates = await exchange_service.get_rates(force_refresh=True)

        # Assert fallback to existing rates
        assert rates is not None, "Should use existing rates"
        assert Currency.SEK in rates, "Existing rates should be preserved"

        # With no existing rates and no fresh cache -> degrade to empty (never
        # raise, never use stale rates).
        exchange_service.rates = {}
        exchange_service.last_update = 0
        with patch.object(
            exchange_service, "_load_cache", AsyncMock(return_value=False)
        ):
            rates = await exchange_service.get_rates(force_refresh=True)
            assert rates == {}, "Should return empty rates when nothing is fresh"


@pytest.mark.asyncio
async def test_convert_currency_same_currency(exchange_service):
    """Test conversion when source and target currencies are the same."""
    # Arrange - No session needed for same currency
    exchange_service.session.get = AsyncMock()

    # Act
    result = await exchange_service.convert(
        amount=100.0, from_currency=Currency.EUR, to_currency=Currency.EUR
    )

    # Assert
    assert (
        result == 100.0
    ), f"Converting to same currency should return original amount, got {result}"
    exchange_service.session.get.assert_not_called(), "API should not be called for same currency conversion"


@pytest.mark.asyncio
async def test_convert_currency_network_error(exchange_service):
    """Test handling of network errors during API calls."""
    # Pre-populate cache with some rate data to test fallback
    exchange_service.rates = {Currency.EUR: 1.0, Currency.SEK: 10.0, Currency.USD: 1.1}
    exchange_service.last_update = time.time()

    # Simulate network error by raising an exception
    network_error = ClientError("Connection error")
    with patch.object(
        exchange_service, "_fetch_ecb_rates", AsyncMock(side_effect=network_error)
    ):
        # Act - Should keep existing (fresh) rates on error
        rates = await exchange_service.get_rates(force_refresh=True)

        # Assert
        assert rates is not None, "Should use existing rates"
        assert Currency.SEK in rates, "Existing rates should be preserved"

        # With empty rates and no fresh cache, the network error is handled
        # gracefully (never propagated) and conversion degrades to empty.
        exchange_service.rates = {}
        exchange_service.last_update = 0
        with patch.object(
            exchange_service, "_load_cache", AsyncMock(return_value=False)
        ):
            rates = await exchange_service.get_rates(force_refresh=True)
            assert rates == {}, "Network error should degrade to empty, not raise"


@pytest.mark.asyncio
async def test_parse_ecb_xml(exchange_service):
    """Test parsing of ECB XML data."""
    # Act
    rates = exchange_service._parse_ecb_xml(MOCK_ECB_XML_RESPONSE)

    # Assert
    assert rates is not None, "Parsed rates should not be None"
    assert Currency.EUR in rates, "EUR should be in rates"
    assert rates[Currency.EUR] == 1.0, "EUR base rate should be 1.0"
    assert "USD" in rates, "USD should be in rates"
    assert rates["USD"] == 1.0828, "USD rate should match mock data"
    assert "SEK" in rates, "SEK should be in rates"
    assert rates["SEK"] == 11.1430, "SEK rate should match mock data"


@pytest.mark.asyncio
async def test_parse_invalid_xml(exchange_service):
    """Test handling of invalid XML data."""
    # Patch the implementation to ensure the error handling works as expected
    with patch.object(ET, "fromstring", side_effect=Exception("XML parsing error")):
        # Act
        rates = exchange_service._parse_ecb_xml(MOCK_INVALID_XML_RESPONSE)

        # Assert
        assert rates is None, "Invalid XML should return None"


@pytest.mark.asyncio
async def test_get_exchange_service_factory():
    """Test the exchange service singleton factory function."""
    # Arrange
    mock_session = MagicMock(spec=ClientSession)

    # Mock get_rates to prevent actual API calls during test
    with patch.object(ExchangeRateService, "get_rates", AsyncMock()):
        # Act - Get the service instance
        service1 = await get_exchange_service(session=mock_session)

        # Get another instance
        service2 = await get_exchange_service(session=mock_session)

        # Assert
        assert isinstance(
            service1, ExchangeRateService
        ), "Factory should return ExchangeRateService"
        assert (
            service1 is service2
        ), "Factory should return the same instance on subsequent calls"

    # Reset the singleton for other tests
    import custom_components.ge_spot.utils.exchange_service

    custom_components.ge_spot.utils.exchange_service._EXCHANGE_SERVICE = None


@pytest.mark.asyncio
async def test_cache_operations(exchange_service, tmp_path):
    """Test cache loading and saving operations."""
    # Setup a temporary cache file
    cache_file = tmp_path / "test_exchange_rates.json"
    exchange_service.cache_file = str(cache_file)

    # Set test rates
    exchange_service.rates = {Currency.EUR: 1.0, Currency.USD: 1.1, Currency.SEK: 10.5}
    exchange_service.last_update = time.time()

    # Test saving cache
    success = await exchange_service._save_cache()
    assert success, "Cache save should succeed"
    assert cache_file.exists(), "Cache file should be created"

    # Clear rates and test loading
    exchange_service.rates = {}
    exchange_service.last_update = 0

    success = await exchange_service._load_cache()
    assert success, "Cache load should succeed"
    assert Currency.EUR in exchange_service.rates, "Loaded rates should include EUR"
    assert (
        exchange_service.rates[Currency.USD] == 1.1
    ), "USD rate should be loaded correctly"
    assert exchange_service.last_update > 0, "Last update timestamp should be set"


@pytest.mark.asyncio
async def test_get_exchange_rate_info(exchange_service):
    """Test getting formatted exchange rate information."""
    # Arrange - set some test rates
    exchange_service.rates = {Currency.EUR: 1.0, Currency.USD: 1.1, Currency.SEK: 10.5}
    exchange_service.last_update = time.time()

    # Act - get info for specific pair
    info = exchange_service.get_exchange_rate_info(Currency.EUR, Currency.SEK)

    # Assert
    assert "rate" in info, "Result should include rate"
    assert info["rate"] == 10.5, "Rate should match the test data"
    assert "formatted" in info, "Result should include formatted rate"
    assert "10.5" in info["formatted"], "Formatted string should include the rate value"

    # Act - get all rates
    all_info = exchange_service.get_exchange_rate_info(Currency.EUR)

    # Assert
    assert "base" in all_info, "All rates result should include base currency"
    assert all_info["base"] == Currency.EUR, "Base currency should match input"
    assert "rates" in all_info, "All rates result should include rates dictionary"
    assert Currency.USD in all_info["rates"], "Rates should include USD"
    assert all_info["rates"][Currency.USD] == 1.1, "USD rate should match test data"


@pytest.mark.asyncio
async def test_convert_currency_missing_rates(exchange_service):
    """Test error handling when rates are missing for requested currencies."""
    # Arrange - set limited but FRESH rates so get_rates returns them as-is
    # (stale rates would be discarded and replaced by cache/fallback).
    exchange_service.rates = {Currency.EUR: 1.0, Currency.USD: 1.1}
    exchange_service.last_update = time.time()

    # Act & Assert - Missing target currency
    with pytest.raises(ValueError) as exc_info:
        await exchange_service.convert(
            amount=100.0,
            from_currency=Currency.EUR,
            to_currency="JPY",  # Not in our test rates
        )

    assert "Missing exchange rates" in str(
        exc_info.value
    ), "Should raise error for missing currency"

    # Act & Assert - Missing source currency
    with pytest.raises(ValueError) as exc_info:
        await exchange_service.convert(
            amount=100.0,
            from_currency="AUD",
            to_currency=Currency.EUR,  # Not in our test rates
        )

    assert "Missing exchange rates" in str(
        exc_info.value
    ), "Should raise error for missing currency"


@pytest.mark.asyncio
async def test_fetch_ecb_rates_uses_instance_session():
    """Regression test: Ensure _fetch_ecb_rates uses self.session, not undefined 'session' variable.

    This test catches a bug where the code used 'session.get()' instead of 'self.session.get()',
    causing a NameError when the exchange service tried to fetch rates.

    Bug history: When updating HTTP_TIMEOUT constant, 'session' was incorrectly used instead of 'self.session'.
    """
    # Arrange - Create service without passing a session (will create its own)
    service = ExchangeRateService()

    # Create a proper mock for the async context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=MOCK_ECB_XML_RESPONSE)

    # Mock session with proper async context manager support
    mock_get = MagicMock()
    mock_get.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get)
    mock_session.close = AsyncMock()  # Mock the close method

    service.session = mock_session

    # Act - Call _fetch_ecb_rates which should use self.session
    try:
        result = await service._fetch_ecb_rates()

        # Assert - Verify the session was used correctly
        # If the code incorrectly used 'session' instead of 'self.session',
        # this would raise NameError: name 'session' is not defined
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args

        # Verify the correct URL and timeout were used
        assert call_args[0][0] == Network.URLs.ECB, "Should call ECB URL"
        assert (
            call_args[1]["timeout"] == Network.Defaults.HTTP_TIMEOUT
        ), "Should use HTTP_TIMEOUT constant"

        # Verify result is parsed correctly (should have parsed the XML)
        assert result is not None, "Should return parsed rates"
        assert isinstance(result, dict), "Should return dictionary of rates"
        assert Currency.USD in result, "Should include USD in parsed rates"

    except NameError as e:
        if "session" in str(e):
            pytest.fail(
                f"BUG DETECTED: Code uses undefined 'session' variable instead of 'self.session': {e}"
            )
        raise


@pytest.mark.asyncio
async def test_fetch_ecb_rates_raises_on_network_error():
    """Regression (issue #68): _fetch_ecb_rates must propagate connection errors.

    Previously the method caught the error and returned None, which silently
    defeated @retry_with_backoff (it only retries on raised exceptions) and
    surfaced the misleading "fetch attempt failed silently" ValueError.
    """
    service = ExchangeRateService()

    # Session whose GET raises a connection error
    mock_get = MagicMock()
    mock_get.__aenter__ = AsyncMock(side_effect=ClientError("Cannot connect to host"))
    mock_get.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get)
    mock_session.close = AsyncMock()
    service.session = mock_session

    # Skip the backoff sleeps so the retries are instant
    with patch(
        "custom_components.ge_spot.api.base.error_handler.asyncio.sleep", AsyncMock()
    ):
        with pytest.raises(ClientError):
            await service._fetch_ecb_rates()


@pytest.mark.asyncio
async def test_fetch_ecb_rates_raises_on_http_error():
    """_fetch_ecb_rates raises (not returns None) on a non-200 response."""
    service = ExchangeRateService()

    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="error")
    mock_get = MagicMock()
    mock_get.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get)
    mock_session.close = AsyncMock()
    service.session = mock_session

    with patch(
        "custom_components.ge_spot.api.base.error_handler.asyncio.sleep", AsyncMock()
    ):
        with pytest.raises(ExchangeRateFetchError):
            await service._fetch_ecb_rates()


@pytest.mark.asyncio
async def test_get_rates_uses_fresh_cache_when_fetch_fails(exchange_service):
    """Failed fetch + a fresh (<= max age) cache -> the cache is used.

    The persistent cache is the self-updating fallback: it is written on every
    successful fetch and survives restarts/upgrades, so no hardcoded rates are
    needed.
    """
    cached = {Currency.EUR: 1.0, Currency.SEK: 11.0, "USD": 1.1}

    def fake_load_cache():
        exchange_service.rates = dict(cached)
        exchange_service.last_update = time.time() - 3600  # 1h old (fresh)
        return True

    exchange_service.rates = {}
    exchange_service.last_update = 0
    with patch.object(
        exchange_service, "_load_cache", AsyncMock(side_effect=fake_load_cache)
    ), patch.object(exchange_service, "_fetch_ecb_rates", AsyncMock(return_value=None)):
        rates = await exchange_service.get_rates(force_refresh=True)

    assert rates == cached, "Should use the fresh cached rates when fetch fails"


@pytest.mark.asyncio
async def test_get_rates_degrades_when_no_fresh_rates(exchange_service):
    """No cache + failed fetch -> empty rates (conversion paused, never raises)."""
    exchange_service.rates = {}
    exchange_service.last_update = 0
    with patch.object(
        exchange_service, "_load_cache", AsyncMock(return_value=False)
    ), patch.object(exchange_service, "_fetch_ecb_rates", AsyncMock(return_value=None)):
        rates = await exchange_service.get_rates(force_refresh=True)

    assert rates == {}, "Should degrade to empty rather than risk stale values"


@pytest.mark.asyncio
async def test_get_rates_discards_stale_in_memory_rates(exchange_service):
    """In-memory rates older than the max age are discarded, never returned."""
    exchange_service.rates = {Currency.EUR: 1.0, Currency.SEK: 10.0}
    exchange_service.last_update = time.time() - (ECB.RATES_MAX_AGE_SECONDS + 3600)

    with patch.object(
        exchange_service, "_load_cache", AsyncMock(return_value=False)
    ), patch.object(exchange_service, "_fetch_ecb_rates", AsyncMock(return_value=None)):
        # Even a non-forced call must not return stale in-memory rates
        rates = await exchange_service.get_rates(force_refresh=False)

    assert rates == {}, "Stale in-memory rates must be discarded"


@pytest.mark.asyncio
async def test_load_cache_rejects_stale(exchange_service, tmp_path):
    """Cache older than the max age is ignored (treated as a miss)."""
    cache_file = tmp_path / "stale_rates.json"
    stale_ts = time.time() - (ECB.RATES_MAX_AGE_SECONDS + 3600)
    cache_file.write_text(
        json.dumps(
            {"rates": {Currency.EUR: 1.0, Currency.SEK: 10.0}, "timestamp": stale_ts}
        )
    )
    exchange_service.cache_file = str(cache_file)
    exchange_service.rates = {}

    loaded = await exchange_service._load_cache()

    assert loaded is False, "Stale cache should not load"
    assert (
        exchange_service.rates == {}
    ), "Rates should remain empty after rejecting stale cache"


@pytest.mark.asyncio
async def test_load_cache_accepts_fresh(exchange_service, tmp_path):
    """Cache within the max age loads normally."""
    cache_file = tmp_path / "fresh_rates.json"
    fresh_ts = time.time() - 3600  # 1h old
    cache_file.write_text(
        json.dumps(
            {"rates": {Currency.EUR: 1.0, Currency.SEK: 10.0}, "timestamp": fresh_ts}
        )
    )
    exchange_service.cache_file = str(cache_file)
    exchange_service.rates = {}

    loaded = await exchange_service._load_cache()

    assert loaded is True
    assert exchange_service.rates[Currency.SEK] == 10.0


@pytest.mark.asyncio
async def test_get_exchange_service_uses_shared_session_and_config_path():
    """Factory uses HA's shared session (not its own) and the config-dir cache."""
    import custom_components.ge_spot.utils.exchange_service as svc_module

    # Ensure a clean singleton
    svc_module._EXCHANGE_SERVICE = None

    mock_hass = MagicMock()
    expected_path = "/config/" + EXCHANGE_RATE_CACHE_FILENAME
    mock_hass.config.path = MagicMock(return_value=expected_path)
    shared_session = MagicMock()

    with patch.object(ExchangeRateService, "get_rates", AsyncMock()), patch(
        "custom_components.ge_spot.utils.exchange_service.async_get_clientsession",
        return_value=shared_session,
    ) as mock_gcs:
        service = await get_exchange_service(hass=mock_hass)

    # Uses the shared HA session, does not open its own, and won't close it
    mock_gcs.assert_called_once_with(mock_hass)
    assert service.session is shared_session
    assert service._owns_session is False
    # Cache stored under the HA config directory (survives upgrades)
    assert service.cache_file == expected_path
    mock_hass.config.path.assert_called_once_with(EXCHANGE_RATE_CACHE_FILENAME)

    # Reset the singleton for other tests
    svc_module._EXCHANGE_SERVICE = None


@pytest.mark.asyncio
async def test_close_only_closes_owned_session():
    """close() closes a session we created, but never an injected (shared) one."""
    # Injected session -> not owned -> must NOT be closed (HA manages it)
    injected = MagicMock()
    injected.close = AsyncMock()
    svc = ExchangeRateService(session=injected)
    assert svc._owns_session is False
    await svc.close()
    injected.close.assert_not_called()
    assert svc.session is injected  # still usable by HA

    # No session injected -> we create and own one -> close() closes it
    svc2 = ExchangeRateService()
    assert svc2._owns_session is True
    created = MagicMock()
    created.close = AsyncMock()
    with patch(
        "custom_components.ge_spot.utils.exchange_service.aiohttp.ClientSession",
        return_value=created,
    ):
        await svc2._ensure_session()
    assert svc2.session is created
    await svc2.close()
    created.close.assert_awaited_once()
    assert svc2.session is None
