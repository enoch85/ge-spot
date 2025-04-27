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
from aiohttp import ClientError, ClientResponseError, ClientSession
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.utils.exchange_service import (
    ExchangeRateService, 
    get_exchange_service,
    ExchangeService  # This is now an alias for ExchangeRateService
)
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.defaults import Defaults
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.const.api import ECB

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
    
    # Create service instance
    service = ExchangeRateService(session=mock_session)
    
    # Reset internal state
    service.rates = {}
    service.last_update = 0
    
    yield service
    
    # Clean up
    if not mock_session.closed:
        await service.close()


@pytest.mark.asyncio
async def test_convert_currency_success(exchange_service):
    """Test successful currency conversion with live rates."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=MOCK_ECB_XML_RESPONSE)
    exchange_service.session.get = AsyncMock(return_value=mock_response)
    
    # Act
    amount = 100.0
    from_currency = Currency.EUR
    to_currency = Currency.SEK
    result = await exchange_service.convert(amount, from_currency, to_currency)
    
    # Assert
    assert result is not None, "Conversion rate should not be None"
    # EUR is the base currency in ECB, so the conversion is direct
    expected_rate = 11.1430  # SEK rate from mock data
    expected_amount = amount * expected_rate
    assert abs(result - expected_amount) < 0.01, f"Expected conversion of 100 EUR → SEK to be ~{expected_amount}, got {result}"
    
    # Verify API was called correctly
    exchange_service.session.get.assert_called_once()


@pytest.mark.asyncio
async def test_convert_currency_caching(exchange_service):
    """Test that rates are cached and not fetched for every conversion."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=MOCK_ECB_XML_RESPONSE)
    exchange_service.session.get = AsyncMock(return_value=mock_response)
    
    # Act - First conversion to load rates
    await exchange_service.convert(
        amount=100.0,
        from_currency=Currency.EUR,
        to_currency=Currency.SEK
    )
    
    # Reset mock to verify it's not called again
    exchange_service.session.get.reset_mock()
    
    # Act - Second conversion should use cached rates
    await exchange_service.convert(
        amount=50.0,
        from_currency=Currency.EUR,
        to_currency=Currency.NOK
    )
    
    # Assert
    exchange_service.session.get.assert_not_called(), "API should not be called again for cached rates"
    
    # Force refresh by simulating old cache
    exchange_service.last_update = 0
    
    # Act - Third conversion should refresh rates
    await exchange_service.convert(
        amount=75.0,
        from_currency=Currency.EUR, 
        to_currency=Currency.SEK
    )
    
    # Assert
    exchange_service.session.get.assert_called_once(), "API should be called again after cache expiry"


@pytest.mark.asyncio
async def test_convert_currency_api_error(exchange_service):
    """Test handling of API errors with appropriate fallback."""
    # Arrange - Simulate API error
    mock_response = MagicMock()
    mock_response.status = 401
    mock_response.text = AsyncMock(return_value="Unauthorized")
    mock_response.raise_for_status = MagicMock(side_effect=ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=401,
        message="401, message='Unauthorized'",
        headers={}
    ))
    exchange_service.session.get = AsyncMock(return_value=mock_response)
    
    # Pre-populate cache with some rate data to test fallback
    exchange_service.rates = {
        Currency.EUR: 1.0,
        Currency.SEK: 10.0,
        Currency.USD: 1.1
    }
    old_timestamp = time.time() - 3600  # 1 hour ago
    exchange_service.last_update = old_timestamp
    
    # Act - Should return error since ExchangeRateService should retry but eventually fail
    with pytest.raises(Exception):
        await exchange_service.get_rates(force_refresh=True)
    
    # But convert should still work with cached rates
    result = await exchange_service.convert(100.0, Currency.EUR, Currency.SEK)
    assert result == 1000.0, "Should fallback to cached rates"


@pytest.mark.asyncio
async def test_convert_currency_same_currency(exchange_service):
    """Test conversion when source and target currencies are the same."""
    # Arrange - No API response needed for same currency
    exchange_service.session.get = AsyncMock()
    
    # Act
    result = await exchange_service.convert(
        amount=100.0,
        from_currency=Currency.EUR,
        to_currency=Currency.EUR
    )
    
    # Assert
    assert result == 100.0, f"Converting to same currency should return original amount, got {result}"
    exchange_service.session.get.assert_not_called(), "API should not be called for same currency conversion"


@pytest.mark.asyncio
async def test_convert_currency_network_error(exchange_service):
    """Test handling of network errors during API calls."""
    # Arrange - Simulate network error
    network_error = ClientError("Connection error")
    exchange_service.session.get = AsyncMock(side_effect=network_error)
    
    # Pre-populate cache with some rate data to test fallback
    exchange_service.rates = {
        Currency.EUR: 1.0,
        Currency.SEK: 10.0,
        Currency.USD: 1.1
    }
    exchange_service.last_update = time.time()
    
    # Act - Should throw error with force_refresh since it can't fall back
    with pytest.raises(ClientError) as exc_info:
        await exchange_service.get_rates(force_refresh=True)
    
    assert "Connection error" in str(exc_info.value), f"Error message should contain details, got {str(exc_info.value)}"
    
    # But should succeed with fallback on existing rates
    rates = await exchange_service.get_rates(force_refresh=False)
    assert rates is not None, "Should return cached rates"
    assert Currency.SEK in rates, "Cached rates should contain expected currencies"


@pytest.mark.asyncio
async def test_parse_ecb_xml(exchange_service):
    """Test parsing of ECB XML data."""
    # Act
    rates = exchange_service._parse_ecb_xml(MOCK_ECB_XML_RESPONSE)
    
    # Assert
    assert rates is not None, "Parsed rates should not be None"
    assert Currency.EUR in rates, "EUR should be in rates"
    assert rates[Currency.EUR] == 1.0, "EUR base rate should be 1.0"
    assert Currency.USD in rates, "USD should be in rates"
    assert rates[Currency.USD] == 1.0828, "USD rate should match mock data"
    assert Currency.SEK in rates, "SEK should be in rates"
    assert rates[Currency.SEK] == 11.1430, "SEK rate should match mock data"


@pytest.mark.asyncio
async def test_parse_invalid_xml(exchange_service):
    """Test handling of invalid XML data."""
    # Act
    rates = exchange_service._parse_ecb_xml(MOCK_INVALID_XML_RESPONSE)
    
    # Assert
    assert rates is None, "Invalid XML should return None"


@pytest.mark.asyncio
async def test_get_exchange_service_factory():
    """Test the exchange service factory function creates the appropriate service."""
    # Arrange
    mock_session = MagicMock(spec=ClientSession)
    
    # Act
    service = await get_exchange_service(session=mock_session)
    
    # Assert
    assert isinstance(service, ExchangeRateService), "Factory should return ExchangeRateService"
    assert service is await get_exchange_service(session=mock_session), "Factory should return the same instance on subsequent calls"


# Add this import to support the test
import time


@pytest.mark.asyncio
async def test_cache_operations(exchange_service, tmp_path):
    """Test cache loading and saving operations."""
    # Setup a temporary cache file
    cache_file = tmp_path / "test_exchange_rates.json"
    exchange_service.cache_file = str(cache_file)
    
    # Set test rates
    exchange_service.rates = {
        Currency.EUR: 1.0,
        Currency.USD: 1.1,
        Currency.SEK: 10.5
    }
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
    assert exchange_service.rates[Currency.USD] == 1.1, "USD rate should be loaded correctly"
    assert exchange_service.last_update > 0, "Last update timestamp should be set"


@pytest.mark.asyncio
async def test_get_exchange_rate_info(exchange_service):
    """Test getting formatted exchange rate information."""
    # Arrange - set some test rates
    exchange_service.rates = {
        Currency.EUR: 1.0,
        Currency.USD: 1.1,
        Currency.SEK: 10.5
    }
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
    # Arrange - set limited rates
    exchange_service.rates = {
        Currency.EUR: 1.0,
        Currency.USD: 1.1
    }
    
    # Act & Assert - Missing target currency
    with pytest.raises(ValueError) as exc_info:
        await exchange_service.convert(
            amount=100.0,
            from_currency=Currency.EUR,
            to_currency="JPY"  # Not in our test rates
        )
    
    assert "Missing exchange rates" in str(exc_info.value), "Should raise error for missing currency"
    
    # Act & Assert - Missing source currency
    with pytest.raises(ValueError) as exc_info:
        await exchange_service.convert(
            amount=100.0,
            from_currency="AUD",  # Not in our test rates
            to_currency=Currency.EUR
        )
    
    assert "Missing exchange rates" in str(exc_info.value), "Should raise error for missing currency"