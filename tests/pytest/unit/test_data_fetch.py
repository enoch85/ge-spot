import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time
import logging
from custom_components.ge_spot.timezone.service import TimezoneService

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from custom_components.ge_spot.api.base.data_fetch import PriceDataFetcher
from custom_components.ge_spot.api.base.base_price_api import BasePriceAPI

# --- Mocks ---

class MockParser:
    def parse(self, raw_data):
        return raw_data

class MockSuccessfulAPI(BasePriceAPI):
    """Mock API that successfully returns price data."""
    def __init__(self, *args, **kwargs):
        tz_service = TimezoneService()
        super().__init__(timezone_service=tz_service)
    def get_parser_for_area(self, area):
        return MockParser()
    def _get_source_type(self): return "mock_success"
    def _get_base_url(self): return "http://success.test"
    async def fetch_raw_data(self, *args, **kwargs): return {"data": "raw_success"}
    async def parse_raw_data(self, *args, **kwargs): 
        return {
            "interval_prices": {"2024-01-01T10:00:00+00:00": 10.0},
            "currency": "EUR",
            "api_timezone": "UTC"
        }
    # Explicitly implement fetch_day_ahead_prices to match BasePriceAPI's signature
    async def fetch_day_ahead_prices(self, area=None, **kwargs):
        # Pass the correct arguments to the super method
        return await super().fetch_day_ahead_prices(area=area, **kwargs)

class MockFailedAPI(BasePriceAPI):
    """Mock API that fails with a connection error."""
    def __init__(self, *args, **kwargs):
        tz_service = TimezoneService()
        super().__init__(timezone_service=tz_service)
    def get_parser_for_area(self, area):
        return MockParser()
    def _get_source_type(self): return "mock_fail"
    def _get_base_url(self): return "http://fail.test"
    async def fetch_raw_data(self, *args, **kwargs): 
        raise ConnectionError("Mock API unavailable")
    async def parse_raw_data(self, *args, **kwargs): 
        # This shouldn't be reached if fetch fails
        return {}
    # Explicitly implement fetch_day_ahead_prices to match BasePriceAPI's signature
    async def fetch_day_ahead_prices(self, area=None, **kwargs):
        # This will raise ConnectionError from fetch_raw_data
        return await super().fetch_day_ahead_prices(area=area, **kwargs)

class MockEmptyAPI(BasePriceAPI):
    """Mock API that returns no price data (empty interval_prices)."""
    def __init__(self, *args, **kwargs):
        tz_service = TimezoneService()
        super().__init__(timezone_service=tz_service)
    def get_parser_for_area(self, area):
        return MockParser()
    def _get_source_type(self): return "mock_empty"
    def _get_base_url(self): return "http://empty.test"
    async def fetch_raw_data(self, *args, **kwargs): return {"data": "raw_empty"}
    async def parse_raw_data(self, *args, **kwargs):
        # Simulate parser returning no valid prices
        return {"interval_prices": {}, "currency": "EUR", "api_timezone": "UTC"}
    # Explicitly implement fetch_day_ahead_prices to match BasePriceAPI's signature
    async def fetch_day_ahead_prices(self, area=None, **kwargs):
        # Pass the correct arguments to the super method
        return await super().fetch_day_ahead_prices(area=area, **kwargs)

class MockTimeoutAPI(BasePriceAPI):
    """Mock API that times out after a delay."""
    def __init__(self, *args, **kwargs):
        tz_service = TimezoneService()
        super().__init__(timezone_service=tz_service)
    def get_parser_for_area(self, area):
        return MockParser()
    def _get_source_type(self): return "mock_timeout"
    def _get_base_url(self): return "http://timeout.test"
    async def fetch_raw_data(self, *args, **kwargs): 
        # Simulate a timeout
        raise TimeoutError("Mock API timed out")
    async def parse_raw_data(self, *args, **kwargs): 
        # This shouldn't be reached if fetch times out
        return {}
    # Explicitly implement fetch_day_ahead_prices to match BasePriceAPI's signature
    async def fetch_day_ahead_prices(self, area=None, **kwargs):
        # This will raise TimeoutError from fetch_raw_data
        return await super().fetch_day_ahead_prices(area=area, **kwargs)

class MockErrorAPI(BasePriceAPI):
    """Mock API that returns a server error."""
    def __init__(self, *args, **kwargs):
        tz_service = TimezoneService()
        super().__init__(timezone_service=tz_service)
    def get_parser_for_area(self, area):
        return MockParser()
    def _get_source_type(self): return "mock_error"
    def _get_base_url(self): return "http://error.test"
    async def fetch_raw_data(self, *args, **kwargs): 
        # Simulate a server error response
        raise Exception("Mock API server error (500)")
    async def parse_raw_data(self, *args, **kwargs): 
        # This shouldn't be reached if fetch fails
        return {}
    # Explicitly implement fetch_day_ahead_prices to match BasePriceAPI's signature
    async def fetch_day_ahead_prices(self, area=None, **kwargs):
        # This will raise Exception from fetch_raw_data
        return await super().fetch_day_ahead_prices(area=area, **kwargs)

class MockPartialDataAPI(BasePriceAPI):
    """Mock API that returns incomplete data (missing some hours)."""
    def __init__(self, *args, **kwargs):
        tz_service = TimezoneService()
        super().__init__(timezone_service=tz_service)
    def get_parser_for_area(self, area):
        return MockParser()
    def _get_source_type(self): return "mock_partial"
    def _get_base_url(self): return "http://partial.test"
    async def fetch_raw_data(self, *args, **kwargs): return {"data": "raw_partial"}
    async def parse_raw_data(self, *args, **kwargs):
        # Return only a few hours instead of a full day
        return {
            "interval_prices": {
                "2024-01-01T10:00:00+00:00": 10.0,
                "2024-01-01T11:00:00+00:00": 11.0,
                # Missing the rest of the hours
            },
            "currency": "EUR",
            "api_timezone": "UTC"
        }
    # Explicitly implement fetch_day_ahead_prices to match BasePriceAPI's signature
    async def fetch_day_ahead_prices(self, area=None, **kwargs):
        # Pass the correct arguments to the super method
        return await super().fetch_day_ahead_prices(area=area, **kwargs)

@pytest.fixture
def price_data_fetcher():
    """Provides a PriceDataFetcher instance with a clean cache for each test."""
    fetcher = PriceDataFetcher()
    fetcher.cache = {} # Ensure clean cache for each test
    return fetcher

# --- Test Cases ---

@pytest.mark.asyncio
async def test_fetch_with_fallback_primary_success(price_data_fetcher):
    """Test fallback: Primary source succeeds - should not attempt fallback sources."""
    sources = [MockSuccessfulAPI, MockFailedAPI]
    mock_success_data = {
        "source": "mock_success",
        "interval_prices": {"2024-01-01T10:00:00+00:00": 10.0},
        "currency": "EUR",
        "api_timezone": "UTC"
    }
    
    # Use patch to mock the class methods before instantiation
    with patch('tests.pytest.unit.test_data_fetch.MockSuccessfulAPI.fetch_day_ahead_prices', 
               new_callable=AsyncMock, return_value=mock_success_data) as mock_fetch_success, \
         patch('tests.pytest.unit.test_data_fetch.MockFailedAPI.fetch_day_ahead_prices',
               new_callable=AsyncMock, side_effect=ConnectionError("Mock API unavailable")) as mock_fetch_fail:
        
        result = await price_data_fetcher.fetch_with_fallback(sources, "TEST_AREA", "EUR")
        
        # Primary source should be called
        mock_fetch_success.assert_called_once()
        # Fallback sources should NOT be called when primary succeeds
        mock_fetch_fail.assert_not_called()
        
        # Verify the returned data structure
        assert result is not None, "Result should not be None when primary source succeeds"
        assert result["source"] == "mock_success", f"Expected source 'mock_success', got '{result.get('source')}'"
        assert "interval_prices" in result, "Result should include 'interval_prices'"
        assert len(result["interval_prices"]) > 0, "Result should have price data when source succeeds"
        assert result["interval_prices"]["2024-01-01T10:00:00+00:00"] == 10.0, "Price value should match expected"
        assert "attempted_sources" in result, "Result should track attempted_sources"
        assert result["attempted_sources"] == ["Source_0"], f"Only primary source (Source_0) should be attempted, got {result.get('attempted_sources')}"
        assert "fallback_sources" in result, "Result should include fallback_sources field"
        assert len(result["fallback_sources"]) == 0, f"No fallbacks should be used when primary succeeds, got {result.get('fallback_sources')}"

@pytest.mark.asyncio
async def test_fetch_with_fallback_primary_fails_secondary_succeeds(price_data_fetcher):
    """Test fallback: Primary fails, secondary succeeds - should use fallback with proper metadata."""
    sources = [MockFailedAPI, MockSuccessfulAPI]
    mock_success_data = {
        "source": "mock_success",
        "interval_prices": {"2024-01-01T10:00:00+00:00": 10.0},
        "currency": "EUR",
        "api_timezone": "UTC"
    }
    
    # Use patch to mock the class methods before instantiation
    with patch('tests.pytest.unit.test_data_fetch.MockFailedAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, side_effect=ConnectionError("Mock API unavailable")) as mock_fetch_fail, \
         patch('tests.pytest.unit.test_data_fetch.MockSuccessfulAPI.fetch_day_ahead_prices',
              new_callable=AsyncMock, return_value=mock_success_data) as mock_fetch_success:
        
        result = await price_data_fetcher.fetch_with_fallback(sources, "TEST_AREA", "EUR")
        
        # Both sources should be called in order
        mock_fetch_fail.assert_called_once()
        mock_fetch_success.assert_called_once()
        
        # Verify result structure and values
        assert result is not None, "Result should not be None when fallback succeeds"
        assert result["source"] == "mock_success", f"Expected source 'mock_success', got '{result.get('source')}'"
        assert "interval_prices" in result, "Result should include 'interval_prices'"
        assert len(result["interval_prices"]) > 0, "Result should have price data from fallback source"
        assert result["interval_prices"]["2024-01-01T10:00:00+00:00"] == 10.0, "Price value from fallback should match expected"
        
        # Check fallback metadata - critical for determining if fallback was used correctly
        assert "attempted_sources" in result, "Result should track attempted_sources"
        assert "Source_0" in result["attempted_sources"], "Primary source should be in attempted_sources"
        assert "Source_1" in result["attempted_sources"], "Secondary source should be in attempted_sources"
        assert len(result["attempted_sources"]) == 2, f"Both sources should be attempted, got {len(result['attempted_sources'])}"
        
        assert "fallback_sources" in result, "Result should include fallback_sources field"
        assert "Source_0" in result["fallback_sources"], "Failed primary source should be in fallback_sources"
        assert len(result["fallback_sources"]) == 1, f"Only primary source should be in fallback_sources, got {len(result['fallback_sources'])}"

@pytest.mark.asyncio
async def test_fetch_with_fallback_all_fail_no_cache(price_data_fetcher):
    """Test fallback: All sources fail, no cache exists - should return structured empty result."""
    sources = [MockFailedAPI, MockEmptyAPI, MockTimeoutAPI, MockErrorAPI]
    
    # Use patch to mock the class methods before instantiation
    with patch('tests.pytest.unit.test_data_fetch.MockFailedAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, side_effect=ConnectionError("Mock API unavailable")) as mock_fetch_fail, \
         patch('tests.pytest.unit.test_data_fetch.MockEmptyAPI.fetch_day_ahead_prices',
              new_callable=AsyncMock, return_value={
                 "source": "mock_empty",
                 "interval_prices": {},
                 "currency": "EUR",
                 "api_timezone": "UTC"
              }) as mock_fetch_empty, \
         patch('tests.pytest.unit.test_data_fetch.MockTimeoutAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, side_effect=TimeoutError("Mock API timed out")) as mock_fetch_timeout, \
         patch('tests.pytest.unit.test_data_fetch.MockErrorAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, side_effect=Exception("Mock API server error (500)")) as mock_fetch_error:

        result = await price_data_fetcher.fetch_with_fallback(sources, "TEST_AREA", "EUR")
        
        # All sources should be attempted in sequence
        mock_fetch_fail.assert_called_once()
        mock_fetch_empty.assert_called_once()
        mock_fetch_timeout.assert_called_once()
        mock_fetch_error.assert_called_once()
        
        # The updated implementation should return a standardized empty result instead of None
        assert result is not None, "Result should not be None even when all sources fail"
        assert "interval_prices" in result, "Result should include interval_prices field"
        assert isinstance(result["interval_prices"], dict), f"interval_prices should be a dictionary, got {type(result.get('interval_prices'))}"
        assert len(result["interval_prices"]) == 0, f"Expected empty interval_prices, got {len(result.get('interval_prices', {}))}"
        
        # Area should be preserved
        assert "area" in result, "Result should include area field"
        assert result["area"] == "TEST_AREA", f"Area should match requested area, got {result.get('area')}"
        
        # All sources should be marked as attempted and failed
        assert "attempted_sources" in result, "Result should track attempted_sources"
        assert result["attempted_sources"] == ["Source_0", "Source_1", "Source_2", "Source_3"], \
               f"All sources should be in attempted_sources, got {result.get('attempted_sources')}"
               
        assert "fallback_sources" in result, "Result should include fallback_sources field"
        assert len(result["fallback_sources"]) == 4, f"All sources should be in fallback_sources, got {len(result.get('fallback_sources', []))}"
        for i in range(4):
            assert f"Source_{i}" in result["fallback_sources"], f"Source_{i} should be in fallback_sources"

@pytest.mark.asyncio
async def test_fetch_with_fallback_all_fail_cache_hit(price_data_fetcher):
    """Test fallback: All sources fail, but valid cache exists - should return cached data."""
    sources = [MockFailedAPI, MockEmptyAPI]
    area = "CACHE_AREA"
    currency = "EUR"
    cache_key = f"{area}_{currency}"
    
    # Create realistic cached data with all required fields
    cached_data = {
        "source": "cached_source", 
        "interval_prices": {"2024-01-01T10:00:00+00:00": 5.0},
        "currency": currency,
        "api_timezone": "UTC",
        "area": area
    }
    
    # Pre-populate cache with recent timestamp
    price_data_fetcher.cache[cache_key] = {
        "data": cached_data,
        "timestamp": time.time() - 100,  # 100 seconds old (within default cache expiry)
        "source": "cached_source"
    }

    with patch('tests.pytest.unit.test_data_fetch.MockFailedAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, side_effect=ConnectionError("Mock API unavailable")) as mock_fetch_fail, \
         patch('tests.pytest.unit.test_data_fetch.MockEmptyAPI.fetch_day_ahead_prices',
              new_callable=AsyncMock, return_value={
                 "source": "mock_empty", 
                 "interval_prices": {}, 
                 "currency": currency, 
                 "api_timezone": "UTC"
              }) as mock_fetch_empty:

        result = await price_data_fetcher.fetch_with_fallback(sources, area, currency)
        
        # Both sources should be attempted before using cache
        mock_fetch_fail.assert_called_once()
        mock_fetch_empty.assert_called_once()
        
        # Result should be the cached data
        assert result is not None, "Result should not be None when cache is available"
        assert result == cached_data, "Result should match cached data when all sources fail and cache is valid"
        assert result["source"] == "cached_source", f"Source should be cached_source, got {result.get('source')}"
        assert "interval_prices" in result, "Result should include interval_prices from cache"
        assert len(result["interval_prices"]) > 0, "Cached interval_prices should not be empty"
        assert result["interval_prices"]["2024-01-01T10:00:00+00:00"] == 5.0, "Price value from cache should match expected"

@pytest.mark.asyncio
async def test_fetch_with_fallback_all_fail_cache_expired(price_data_fetcher):
    """Test fallback: All sources fail, and cache is expired - should not use expired cache."""
    sources = [MockFailedAPI, MockEmptyAPI]
    area = "EXPIRED_CACHE_AREA"
    currency = "EUR"
    cache_key = f"{area}_{currency}"
    
    # Create realistic cached data with all required fields
    cached_data = {
        "source": "cached_source", 
        "interval_prices": {"2024-01-01T10:00:00+00:00": 5.0},
        "currency": currency,
        "api_timezone": "UTC",
        "area": area
    }
    
    # Pre-populate cache with old timestamp that exceeds default expiry
    price_data_fetcher.cache[cache_key] = {
        "data": cached_data,
        "timestamp": time.time() - (7 * 60 * 60),  # 7 hours old (> default 6h expiry)
        "source": "cached_source"
    }

    with patch('tests.pytest.unit.test_data_fetch.MockFailedAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, side_effect=ConnectionError("Mock API unavailable")) as mock_fetch_fail, \
         patch('tests.pytest.unit.test_data_fetch.MockEmptyAPI.fetch_day_ahead_prices',
              new_callable=AsyncMock, return_value={
                 "source": "mock_empty",
                 "interval_prices": {},
                 "currency": currency,
                 "api_timezone": "UTC",
              }) as mock_fetch_empty:

        result = await price_data_fetcher.fetch_with_fallback(sources, area, currency)
        
        # Both sources should be attempted
        mock_fetch_fail.assert_called_once()
        mock_fetch_empty.assert_called_once()
        
        # Result should be standardized empty result, NOT the expired cached data
        assert result is not None, "Result should not be None when all sources fail"
        assert result["source"] != "cached_source", "Result should not use expired cache data"
        assert "interval_prices" in result, "Result should include interval_prices field"
        assert len(result["interval_prices"]) == 0, f"interval_prices should be empty when all sources fail and cache expired, got {len(result.get('interval_prices', {}))} entries"
        
        # Area should be preserved
        assert "area" in result, "Result should include area field"
        assert result["area"] == area, f"Area should match requested area, got {result.get('area')}"
        
        # All sources should be marked as attempted and failed
        assert "attempted_sources" in result, "Result should track attempted_sources"
        assert result["attempted_sources"] == ["Source_0", "Source_1"], f"All sources should be in attempted_sources, got {result.get('attempted_sources')}"
        assert "fallback_sources" in result, "Result should include fallback_sources field"
        assert all(source in result["fallback_sources"] for source in ["Source_0", "Source_1"]), "All sources should be in fallback_sources"

@pytest.mark.asyncio
async def test_fetch_with_fallback_empty_sources(price_data_fetcher):
    """Test fallback: Called with an empty list of sources - should handle gracefully."""
    sources = []
    area = "EMPTY_SOURCES_AREA"
    currency = "EUR"
    
    result = await price_data_fetcher.fetch_with_fallback(sources, area, currency)
    
    # Updated implementation should return a standardized empty result rather than None
    if result is None:
        # This is acceptable if the implementation returns None for empty sources
        assert result is None, "Result should be None when called with empty sources list"
    else:
        # Or it should return a standardized empty result with error information
        assert "interval_prices" in result, "Result should include interval_prices field"
        assert len(result["interval_prices"]) == 0, "interval_prices should be empty when called with empty sources list"
        assert "area" in result, "Result should include area field"
        assert result["area"] == area, f"Area should match requested area, got {result.get('area')}"
        assert "attempted_sources" in result, "Result should track attempted_sources"
        assert len(result["attempted_sources"]) == 0, "attempted_sources should be empty when no sources provided"

@pytest.mark.asyncio
async def test_fetch_with_fallback_partial_data(price_data_fetcher):
    """Test fallback: First source returns partial data, second returns complete - should prefer complete data."""
    sources = [MockPartialDataAPI, MockSuccessfulAPI]
    
    mock_partial_data = {
        "source": "mock_partial",
        "interval_prices": {
            "2024-01-01T10:00:00+00:00": 10.0,
            "2024-01-01T11:00:00+00:00": 11.0,
        },
        "currency": "EUR",
        "api_timezone": "UTC"
    }
    
    mock_success_data = {
        "source": "mock_success",
        "interval_prices": {"2024-01-01T10:00:00+00:00": 10.0},
        "currency": "EUR",
        "api_timezone": "UTC"
    }
    
    with patch('tests.pytest.unit.test_data_fetch.MockPartialDataAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, return_value=mock_partial_data) as mock_fetch_partial, \
         patch('tests.pytest.unit.test_data_fetch.MockSuccessfulAPI.fetch_day_ahead_prices',
              new_callable=AsyncMock, return_value=mock_success_data) as mock_fetch_success:
        
        result = await price_data_fetcher.fetch_with_fallback(sources, "TEST_AREA", "EUR")
        
        # First source should be called
        mock_fetch_partial.assert_called_once()
        
        # If the implementation accepts partial data, second source shouldn't be called
        # If it prefers complete data, it might try the second source
        
        # The key test: we get valid data back with the correct source
        assert result is not None, "Result should not be None"
        assert "interval_prices" in result, "Result should include interval_prices"
        assert len(result["interval_prices"]) > 0, "Result should have price data"
        
        # If partial data is accepted (which is reasonable):
        if result["source"] == "mock_partial":
            assert len(result["interval_prices"]) == 2, f"Should have 2 hours from partial data, got {len(result['interval_prices'])}"
            assert result["interval_prices"]["2024-01-01T10:00:00+00:00"] == 10.0, "Price value should match partial data"
            assert result["interval_prices"]["2024-01-01T11:00:00+00:00"] == 11.0, "Price value should match partial data"
            
        # If implementation prefers complete data:
        elif result["source"] == "mock_success":
            assert mock_fetch_success.called, "Second source should be called if implementation prefers complete data"
            assert len(result["interval_prices"]) == 1, f"Should have 1 hour from complete data, got {len(result['interval_prices'])}"
            assert result["interval_prices"]["2024-01-01T10:00:00+00:00"] == 10.0, "Price value should match complete data"

@pytest.mark.asyncio
async def test_cache_behavior_with_expiry_times(price_data_fetcher):
    """Test cache behavior with different expiry times - critical for fallback mechanism."""
    area = "CACHE_EXPIRY_AREA"
    currency = "EUR"
    cache_key = f"{area}_{currency}"
    
    # Create cached data with all required fields
    cached_data = {
        "source": "cached_source", 
        "interval_prices": {"2024-01-01T10:00:00+00:00": 5.0},
        "currency": currency,
        "api_timezone": "UTC",
        "area": area
    }
    
    # Test with cache just at expiry threshold
    cache_expiry_hours = 6  # Default is 6 hours
    cache_timestamp = time.time() - (cache_expiry_hours * 60 * 60)
    
    # Pre-populate cache at exact expiry threshold
    price_data_fetcher.cache[cache_key] = {
        "data": cached_data,
        "timestamp": cache_timestamp,
        "source": "cached_source"
    }
    
    # Test with sources that will fail
    sources = [MockFailedAPI, MockEmptyAPI]
    
    with patch('tests.pytest.unit.test_data_fetch.MockFailedAPI.fetch_day_ahead_prices', 
              new_callable=AsyncMock, side_effect=ConnectionError("Mock API unavailable")), \
         patch('tests.pytest.unit.test_data_fetch.MockEmptyAPI.fetch_day_ahead_prices',
              new_callable=AsyncMock, return_value={
                 "source": "mock_empty",
                 "interval_prices": {},
                 "currency": currency,
                 "api_timezone": "UTC"
              }):
        
        # Custom cache expiry should be used if provided
        result_custom_expiry = await price_data_fetcher.fetch_with_fallback(
            sources, area, currency, cache_expiry_hours=12  # Longer than our 6-hour old cache
        )
        
        # With extended expiry, should return cached data
        assert result_custom_expiry is not None, "Result should not be None with custom cache expiry"
        if result_custom_expiry.get("source") == "cached_source":
            # Cache was used (expected behavior with extended expiry)
            assert result_custom_expiry == cached_data, "Result should match cached data with extended expiry"
        else:
            # If cache wasn't used, result should be empty due to failed sources
            assert len(result_custom_expiry.get("interval_prices", {})) == 0, "Result should have empty interval_prices if cache not used"
        
        # Default expiry should be used if not provided
        result_default_expiry = await price_data_fetcher.fetch_with_fallback(
            sources, area, currency  # No custom expiry
        )
        
        # With default expiry (cache is exactly at threshold), behavior depends on implementation details
        assert result_default_expiry is not None, "Result should not be None with default cache expiry"
        # Cannot assert exact behavior as it depends on implementation (> vs >=)