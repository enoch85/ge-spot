import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time

from custom_components.ge_spot.api.base.data_fetch import PriceDataFetcher
from custom_components.ge_spot.api.base.base_price_api import BasePriceAPI

# --- Mocks ---

class MockSuccessfulAPI(BasePriceAPI):
    def _get_source_type(self): return "mock_success"
    def _get_base_url(self): return "http://success.test"
    async def fetch_raw_data(self, *args, **kwargs): return {"data": "raw_success"}
    async def parse_raw_data(self, *args, **kwargs): 
        return {
            "hourly_prices": {"2024-01-01T10:00:00+00:00": 10.0},
            "currency": "EUR",
            "api_timezone": "UTC"
        }
    # The base fetch_day_ahead_prices is now simple enough we might not need to mock it heavily

class MockFailedAPI(BasePriceAPI):
    def _get_source_type(self): return "mock_fail"
    def _get_base_url(self): return "http://fail.test"
    async def fetch_raw_data(self, *args, **kwargs): 
        raise ConnectionError("Mock API unavailable")
    async def parse_raw_data(self, *args, **kwargs): 
        # This shouldn't be reached if fetch fails
        return {}

class MockEmptyAPI(BasePriceAPI):
    def _get_source_type(self): return "mock_empty"
    def _get_base_url(self): return "http://empty.test"
    async def fetch_raw_data(self, *args, **kwargs): return {"data": "raw_empty"}
    async def parse_raw_data(self, *args, **kwargs):
        # Simulate parser returning no valid prices
        return {"hourly_prices": {}, "currency": "EUR", "api_timezone": "UTC"}

@pytest.fixture
def price_data_fetcher():
    """Provides a PriceDataFetcher instance."""
    fetcher = PriceDataFetcher()
    fetcher.cache = {} # Ensure clean cache for each test
    return fetcher

# --- Test Cases ---

@pytest.mark.asyncio
async def test_fetch_with_fallback_primary_success(price_data_fetcher):
    """Test fallback: Primary source succeeds."""
    sources = [MockSuccessfulAPI, MockFailedAPI]
    with patch.object(MockSuccessfulAPI, 'fetch_day_ahead_prices', 
                      return_value=AsyncMock(return_value={
                          "source": "mock_success",
                          "hourly_prices": {"2024-01-01T10:00:00+00:00": 10.0},
                          "currency": "EUR",
                          "api_timezone": "UTC"
                      })) as mock_fetch_success, \
         patch.object(MockFailedAPI, 'fetch_day_ahead_prices') as mock_fetch_fail:
        
        result = await price_data_fetcher.fetch_with_fallback(sources, "TEST_AREA", "EUR")
        
        mock_fetch_success.assert_called_once()
        mock_fetch_fail.assert_not_called() # Fallback should NOT be called
        assert result is not None
        assert result["source"] == "mock_success"
        assert "attempted_sources" not in result # fetch_with_fallback doesn't add these keys
        assert "fallback_sources" not in result

@pytest.mark.asyncio
async def test_fetch_with_fallback_primary_fails_secondary_succeeds(price_data_fetcher):
    """Test fallback: Primary fails, secondary succeeds."""
    sources = [MockFailedAPI, MockSuccessfulAPI]
    with patch.object(MockFailedAPI, 'fetch_day_ahead_prices', 
                      side_effect=ConnectionError("Mock API unavailable")) as mock_fetch_fail, \
         patch.object(MockSuccessfulAPI, 'fetch_day_ahead_prices', 
                      return_value=AsyncMock(return_value={
                          "source": "mock_success",
                          "hourly_prices": {"2024-01-01T10:00:00+00:00": 10.0},
                          "currency": "EUR",
                          "api_timezone": "UTC"
                      })) as mock_fetch_success:
        
        result = await price_data_fetcher.fetch_with_fallback(sources, "TEST_AREA", "EUR")
        
        mock_fetch_fail.assert_called_once()
        mock_fetch_success.assert_called_once() # Fallback IS called
        assert result is not None
        assert result["source"] == "mock_success"

@pytest.mark.asyncio
async def test_fetch_with_fallback_all_fail_no_cache(price_data_fetcher):
    """Test fallback: All sources fail, no cache exists."""
    sources = [MockFailedAPI, MockEmptyAPI] # Use empty as second failure type
    with patch.object(MockFailedAPI, 'fetch_day_ahead_prices', 
                      side_effect=ConnectionError("Mock API unavailable")) as mock_fetch_fail, \
         patch.object(MockEmptyAPI, 'fetch_day_ahead_prices', 
                      return_value=AsyncMock(return_value={
                          "source": "mock_empty",
                          "hourly_prices": {},
                          "currency": "EUR",
                          "api_timezone": "UTC"
                      })) as mock_fetch_empty:

        result = await price_data_fetcher.fetch_with_fallback(sources, "TEST_AREA", "EUR")
        
        mock_fetch_fail.assert_called_once()
        mock_fetch_empty.assert_called_once()
        assert result is None # Should return None when all fail and no cache

@pytest.mark.asyncio
async def test_fetch_with_fallback_all_fail_cache_hit(price_data_fetcher):
    """Test fallback: All sources fail, but valid cache exists."""
    sources = [MockFailedAPI, MockEmptyAPI]
    area = "CACHE_AREA"
    currency = "EUR"
    cache_key = f"{area}_{currency}"
    cached_data = {
        "source": "cached_source", 
        "hourly_prices": {"2024-01-01T10:00:00+00:00": 5.0},
        "currency": currency,
        "api_timezone": "UTC"
    }
    # Pre-populate cache
    price_data_fetcher.cache[cache_key] = {
        "data": cached_data,
        "timestamp": time.time() - 100, # Recently cached
        "source": "cached_source"
    }

    with patch.object(MockFailedAPI, 'fetch_day_ahead_prices', side_effect=ConnectionError("Fail1")) as mock_fetch1, \
         patch.object(MockEmptyAPI, 'fetch_day_ahead_prices', return_value=AsyncMock(return_value={
             "source": "mock_empty", "hourly_prices": {}, "currency": currency, "api_timezone": "UTC"
         })) as mock_fetch2:

        result = await price_data_fetcher.fetch_with_fallback(sources, area, currency)
        
        mock_fetch1.assert_called_once()
        mock_fetch2.assert_called_once()
        assert result is not None
        assert result == cached_data # Should return the cached data object
        # The fetcher itself doesn't add the 'using_cached_data' flag, the Manager does
        # assert result.get("using_cached_data") is True 

@pytest.mark.asyncio
async def test_fetch_with_fallback_all_fail_cache_expired(price_data_fetcher):
    """Test fallback: All sources fail, and cache is expired."""
    sources = [MockFailedAPI, MockEmptyAPI]
    area = "EXPIRED_CACHE_AREA"
    currency = "EUR"
    cache_key = f"{area}_{currency}"
    cached_data = {"source": "cached_source", "hourly_prices": {"2024-01-01T10:00:00+00:00": 5.0}}
    # Pre-populate cache with old timestamp
    price_data_fetcher.cache[cache_key] = {
        "data": cached_data,
        "timestamp": time.time() - (7 * 60 * 60), # 7 hours old > default 6h expiry
        "source": "cached_source"
    }

    with patch.object(MockFailedAPI, 'fetch_day_ahead_prices', side_effect=ConnectionError("Fail1")) as mock_fetch1, \
         patch.object(MockEmptyAPI, 'fetch_day_ahead_prices', return_value=AsyncMock(return_value={
             "source": "mock_empty", "hourly_prices": {}, "currency": currency, "api_timezone": "UTC"
         })) as mock_fetch2:

        result = await price_data_fetcher.fetch_with_fallback(sources, area, currency)
        
        mock_fetch1.assert_called_once()
        mock_fetch2.assert_called_once()
        assert result is None # Should return None as cache is expired

@pytest.mark.asyncio
async def test_fetch_with_fallback_empty_sources(price_data_fetcher):
    """Test fallback: Called with an empty list of sources."""
    sources = []
    result = await price_data_fetcher.fetch_with_fallback(sources, "ANY_AREA", "EUR")
    assert result is None

# TODO: Add test for fallback with cache hit - DONE
# TODO: Add test for fallback with expired cache - DONE
# TODO: Add test for empty sources list - DONE 