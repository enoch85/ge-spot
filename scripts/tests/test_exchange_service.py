import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import time
import os
import json

from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.const.currencies import Currency

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
        assert rates == cache_data["rates"]
        assert Currency.CENTS in rates # Should be added if missing

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

# No TODOs left here