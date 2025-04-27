import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import time
import os
import json
import xml.etree.ElementTree as ET

from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.const.currencies import Currency

# Sample ECB XML response with real-world exchange rates
ECB_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
    <gesmes:subject>Reference rates</gesmes:subject>
    <gesmes:Sender>
        <gesmes:name>European Central Bank</gesmes:name>
    </gesmes:Sender>
    <Cube>
        <Cube time="2023-04-26">
            <Cube currency="USD" rate="1.0965"/>
            <Cube currency="JPY" rate="147.79"/>
            <Cube currency="BGN" rate="1.9558"/>
            <Cube currency="CZK" rate="24.016"/>
            <Cube currency="DKK" rate="7.4450"/>
            <Cube currency="GBP" rate="0.87980"/>
            <Cube currency="HUF" rate="373.05"/>
            <Cube currency="PLN" rate="4.5953"/>
            <Cube currency="RON" rate="4.9710"/>
            <Cube currency="SEK" rate="11.3355"/>
            <Cube currency="CHF" rate="0.9784"/>
            <Cube currency="ISK" rate="150.10"/>
            <Cube currency="NOK" rate="11.4710"/>
            <Cube currency="HRK" rate="7.5475"/>
            <Cube currency="TRY" rate="21.2886"/>
            <Cube currency="AUD" rate="1.6428"/>
            <Cube currency="BRL" rate="5.4982"/>
            <Cube currency="CAD" rate="1.4938"/>
            <Cube currency="CNY" rate="7.6425"/>
            <Cube currency="HKD" rate="8.6062"/>
            <Cube currency="IDR" rate="16257.27"/>
            <Cube currency="ILS" rate="4.0318"/>
            <Cube currency="INR" rate="90.0850"/>
            <Cube currency="KRW" rate="1465.06"/>
            <Cube currency="MXN" rate="19.8442"/>
            <Cube currency="MYR" rate="4.9025"/>
            <Cube currency="NZD" rate="1.7860"/>
            <Cube currency="PHP" rate="60.919"/>
            <Cube currency="SGD" rate="1.4665"/>
            <Cube currency="THB" rate="37.585"/>
            <Cube currency="ZAR" rate="19.9093"/>
        </Cube>
    </Cube>
</gesmes:Envelope>
"""

# Sample fetched rates
MOCK_RATES = {
    Currency.EUR: 1.0,
    Currency.USD: 1.1,
    Currency.SEK: 11.5,
    Currency.NOK: 11.8,
    Currency.DKK: 7.45,
    Currency.CENTS: 100.0 # Ensure cents is present
}

@pytest.fixture
def exchange_service(tmp_path):
    """Provides an ExchangeRateService instance with mocked fetching and temp cache file."""
    cache_file = tmp_path / "test_cache.json"
    service = ExchangeRateService(cache_file=str(cache_file))
    # Pre-populate rates to avoid actual fetching in basic tests
    service.rates = MOCK_RATES
    service.last_update = time.time()
    return service

@pytest.fixture
def realistic_exchange_service(tmp_path):
    """Provides an ExchangeRateService instance that uses real ECB XML data without network access.
    
    This fixture creates a service that processes actual ECB XML data format,
    giving tests more realistic behavior while still being deterministic and
    not requiring network access.
    """
    cache_file = tmp_path / "realistic_test_cache.json"
    service = ExchangeRateService(cache_file=str(cache_file))
    
    # Use the real _parse_ecb_xml method to parse our sample data
    rates = service._parse_ecb_xml(ECB_XML_SAMPLE)
    
    # Manually set the rates and update timestamp
    service.rates = rates
    service.last_update = time.time()
    return service

# --- Test Cases ---

@pytest.mark.asyncio
async def test_convert_eur_to_sek(exchange_service):
    """Test basic conversion from EUR to SEK."""
    amount = 10.0
    from_curr = Currency.EUR
    to_curr = Currency.SEK
    expected = amount / MOCK_RATES[from_curr] * MOCK_RATES[to_curr] # 10 / 1.0 * 11.5 = 115.0
    
    converted = await exchange_service.convert(amount, from_curr, to_curr)
    assert converted == pytest.approx(expected)

@pytest.mark.asyncio
async def test_convert_sek_to_eur(exchange_service):
    """Test basic conversion from SEK to EUR."""
    amount = 115.0
    from_curr = Currency.SEK
    to_curr = Currency.EUR
    expected = amount / MOCK_RATES[from_curr] * MOCK_RATES[to_curr] # 115.0 / 11.5 * 1.0 = 10.0
    
    converted = await exchange_service.convert(amount, from_curr, to_curr)
    assert converted == pytest.approx(expected)

@pytest.mark.asyncio
async def test_convert_same_currency(exchange_service):
    """Test conversion when from and to currency are the same."""
    amount = 50.0
    from_curr = Currency.USD
    to_curr = Currency.USD
    
    converted = await exchange_service.convert(amount, from_curr, to_curr)
    assert converted == amount

@pytest.mark.asyncio
async def test_convert_eur_to_cents(exchange_service):
    """Test conversion from EUR to CENTS (subunit)."""
    # Note: The current implementation only explicitly handles USD <-> CENTS.
    # It uses the generic EUR-based conversion otherwise, relying on CENTS rate = 100.0
    amount = 1.23
    from_curr = Currency.EUR
    to_curr = Currency.CENTS
    # Expected: 1.23 / 1.0 * 100.0 = 123.0
    expected = amount / MOCK_RATES[from_curr] * MOCK_RATES[to_curr]
    
    converted = await exchange_service.convert(amount, from_curr, to_curr)
    assert converted == pytest.approx(expected)

@pytest.mark.asyncio
async def test_convert_cents_to_eur(exchange_service):
    """Test conversion from CENTS to EUR (subunit)."""
    # Note: The current implementation only explicitly handles USD <-> CENTS.
    amount = 123.0
    from_curr = Currency.CENTS
    to_curr = Currency.EUR
    # Expected: 123.0 / 100.0 * 1.0 = 1.23
    expected = amount / MOCK_RATES[from_curr] * MOCK_RATES[to_curr]
    
    converted = await exchange_service.convert(amount, from_curr, to_curr)
    assert converted == pytest.approx(expected)

@pytest.mark.asyncio
async def test_convert_missing_rate(exchange_service):
    """Test conversion fails if a rate is missing."""
    amount = 10.0
    from_curr = Currency.EUR
    to_curr = "XYZ" # Missing currency
    
    with pytest.raises(ValueError, match="Missing exchange rates"): 
        await exchange_service.convert(amount, from_curr, to_curr)

@pytest.mark.asyncio
async def test_get_rates_cache_load(exchange_service, tmp_path):
    """Test that get_rates loads from a valid cache file."""
    cache_file = tmp_path / "cache_load.json"
    service = ExchangeRateService(cache_file=str(cache_file))
    
    # Create a dummy cache file
    cache_data = {"rates": {Currency.EUR: 1.0, Currency.GBP: 0.85}, "timestamp": time.time() - 300}
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
        
    # Patch fetch to ensure it's not called
    with patch.object(service, '_fetch_ecb_rates', new_callable=AsyncMock) as mock_fetch:
        rates = await service.get_rates()
        mock_fetch.assert_not_called()
        
        # Check the original rates are present (not doing exact equality because service adds CENTS)
        for curr, rate in cache_data["rates"].items():
            assert rates[curr] == rate
            
        # Verify CENTS is added (as the service automatically adds this)
        assert Currency.CENTS in rates
        assert rates[Currency.CENTS] == 100.0

@pytest.mark.asyncio
async def test_get_rates_fetch_on_no_cache(exchange_service, tmp_path):
    """Test that get_rates fetches fresh data if cache doesn't exist."""
    cache_file = tmp_path / "no_cache.json"
    service = ExchangeRateService(cache_file=str(cache_file))
    assert not os.path.exists(cache_file)
    
    # Patch fetch to return mock data
    with patch.object(service, '_fetch_ecb_rates', new_callable=AsyncMock, return_value=MOCK_RATES) as mock_fetch, \
         patch.object(service, '_save_cache', new_callable=AsyncMock) as mock_save:
        rates = await service.get_rates()
        mock_fetch.assert_called_once()
        mock_save.assert_called_once()
        assert rates == MOCK_RATES

@pytest.mark.asyncio
async def test_get_rates_fetch_on_force_refresh(exchange_service, tmp_path):
    """Test that get_rates fetches fresh data when force_refresh is True."""
    cache_file = tmp_path / "force_refresh_cache.json"
    service = ExchangeRateService(cache_file=str(cache_file))
    
    # Create a dummy cache file
    cache_data = {"rates": {Currency.EUR: 1.0, Currency.GBP: 0.85}, "timestamp": time.time() - 300}
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
        
    # Patch fetch to return different mock data
    new_rates = {Currency.EUR: 1.0, Currency.JPY: 150.0}
    with patch.object(service, '_fetch_ecb_rates', new_callable=AsyncMock, return_value=new_rates) as mock_fetch, \
         patch.object(service, '_save_cache', new_callable=AsyncMock) as mock_save:
        rates = await service.get_rates(force_refresh=True)
        mock_fetch.assert_called_once()
        mock_save.assert_called_once()
        assert rates == new_rates

@pytest.mark.asyncio
async def test_convert_with_realistic_rates(realistic_exchange_service):
    """Test currency conversion using realistic ECB rates parsed from XML."""
    # Get the real SEK rate from the ECB XML sample (SEK rate = 11.3355)
    amount = 100.0
    from_curr = Currency.EUR
    to_curr = Currency.SEK
    
    converted = await realistic_exchange_service.convert(amount, from_curr, to_curr)
    assert converted == pytest.approx(1133.55)  # 100 EUR = 1133.55 SEK at rate 11.3355

@pytest.mark.asyncio
async def test_convert_with_realistic_rates_reverse(realistic_exchange_service):
    """Test reverse currency conversion using realistic ECB rates parsed from XML."""
    # Convert SEK to EUR using the real rate from ECB XML sample
    amount = 1133.55
    from_curr = Currency.SEK
    to_curr = Currency.EUR
    
    converted = await realistic_exchange_service.convert(amount, from_curr, to_curr)
    assert converted == pytest.approx(100.0)  # 1133.55 SEK = 100 EUR at rate 11.3355

@pytest.mark.asyncio
async def test_parse_ecb_xml():
    """Test the XML parsing functionality with our sample data."""
    service = ExchangeRateService()
    rates = service._parse_ecb_xml(ECB_XML_SAMPLE)
    
    # Verify we have the expected number of currencies
    assert len(rates) > 30  # Should be 31 currencies + EUR + CENTS
    
    # Check some specific rates from our sample
    assert rates[Currency.EUR] == 1.0  # Base currency
    assert rates[Currency.USD] == pytest.approx(1.0965)
    assert rates[Currency.SEK] == pytest.approx(11.3355)
    assert rates[Currency.CENTS] == 100.0  # Special case
    
    # Verify some conversions based on the parsed rates
    # 100 EUR to USD: 100 / 1.0 * 1.0965 = 109.65 USD
    assert (100.0 / rates[Currency.EUR] * rates[Currency.USD]) == pytest.approx(109.65)