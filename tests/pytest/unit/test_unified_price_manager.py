#!/usr/bin/env python3
"""Tests for the UnifiedPriceManager functionality.

These tests verify real-world behavior of the UnifiedPriceManager to ensure it:
1. Correctly fetches data from appropriate sources
2. Properly handles fallback scenarios when primary sources fail
3. Manages cache with appropriate expiry times
4. Handles error scenarios gracefully without crashing
5. Processes and validates data from different sources consistently

If any test fails, investigate and fix the core implementation rather than adapting tests.
"""
import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock, patch, AsyncMock, call
from datetime import datetime, timedelta, timezone
import pytest
import json

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.coordinator.unified_price_manager import UnifiedPriceManager
from tests.lib.mocks.hass import MockHass
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.defaults import Defaults
from custom_components.ge_spot.const.network import Network
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.const.currencies import Currency

# Mock data for successful fetch
MOCK_SUCCESS_RESULT = {
    "data_source": Source.NORDPOOL,
    "area": "SE1",
    "currency": "SEK", # Original currency from source
    "hourly_prices": {"2025-04-26T10:00:00+00:00": 1.0, "2025-04-26T11:00:00+00:00": 2.0},
    "attempted_sources": [Source.NORDPOOL],
    "error": None,
}

# Mock data for processed result
MOCK_PROCESSED_RESULT = {
    "source": Source.NORDPOOL, # Renamed from data_source
    "area": "SE1",
    "target_currency": "SEK", # Added target currency
    "hourly_prices": {"2025-04-26T10:00:00+02:00": 1.1, "2025-04-26T11:00:00+02:00": 2.2}, # Example processed data
    "attempted_sources": [Source.NORDPOOL],
    "fallback_sources": [],
    "using_cached_data": False,
    "has_data": True,
    "last_update": "2025-04-26T12:00:00+00:00", # Example timestamp
    # Other keys added by DataProcessor
}

# Mock data for cached result (similar structure to processed)
MOCK_CACHED_RESULT = {
    **MOCK_PROCESSED_RESULT, # Base it on processed structure
    "using_cached_data": True,
    "last_update": "2025-04-26T11:30:00+00:00", # Older timestamp
}

# Mock data for failed fetch
MOCK_FAILURE_RESULT = {
    "data_source": "None",
    "area": "SE1",
    "currency": "SEK",
    "hourly_prices": {},
    "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
    "error": "Failed to fetch from all sources",
}

# Mock data for empty processed result
MOCK_EMPTY_PROCESSED_RESULT = {
    "source": "None",
    "area": "SE1",
    "target_currency": "SEK",
    "hourly_prices": {},
    "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
    "fallback_sources": [Source.NORDPOOL, Source.ENTSOE],
    "using_cached_data": False,
    "has_data": False,
    "last_update": "2025-04-26T12:00:00+00:00", # Example timestamp
    "error": "Failed to fetch from all sources",
    # Other keys added by DataProcessor when processing empty data
}


@pytest.fixture(autouse=True)
def auto_mock_core_dependencies():
    """Automatically mock core dependencies used by UnifiedPriceManager."""
    # Patch the global rate limiting dictionary to isolate tests
    with patch('custom_components.ge_spot.coordinator.unified_price_manager._LAST_FETCH_TIME', new_callable=dict) as mock_last_fetch_time, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.FallbackManager', new_callable=MagicMock) as mock_fallback_manager, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.CacheManager', new_callable=MagicMock) as mock_cache_manager, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.DataProcessor', new_callable=MagicMock) as mock_data_processor, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.TimezoneService', new_callable=MagicMock) as mock_tz_service, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.get_exchange_service', new_callable=AsyncMock) as mock_get_exchange_service, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.dt_util.now') as mock_now, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.async_get_clientsession') as mock_get_session, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.get_sources_for_region') as mock_get_sources:

        # Configure default return values for mocks
        mock_get_sources.return_value = [Source.NORDPOOL, Source.ENTSOE]
        mock_fallback_manager.return_value.fetch_with_fallbacks = AsyncMock(return_value=MOCK_SUCCESS_RESULT)
        mock_cache_manager.return_value.get_data = MagicMock(return_value=None)
        mock_cache_manager.return_value.update_cache = MagicMock()
        mock_data_processor.return_value.process = AsyncMock(return_value=MOCK_PROCESSED_RESULT)
        mock_tz_service.return_value = MagicMock() # Basic mock for TimezoneService instance
        mock_get_exchange_service.return_value = AsyncMock() # Mock the service instance itself
        mock_now.return_value = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        mock_get_session.return_value = MagicMock() # Mock the aiohttp session

        yield {
            "last_fetch_time": mock_last_fetch_time, # Include the patched dict if needed
            "fallback_manager": mock_fallback_manager,
            "cache_manager": mock_cache_manager,
            "data_processor": mock_data_processor,
            "tz_service": mock_tz_service,
            "get_exchange_service": mock_get_exchange_service,
            "now": mock_now,
            "get_session": mock_get_session,
            "get_sources": mock_get_sources,
        }


class TestUnifiedPriceManager:
    """Test the UnifiedPriceManager class with real-world scenarios."""

    @pytest.fixture
    def manager(self, auto_mock_core_dependencies):
        """Provides an initialized UnifiedPriceManager instance for tests."""
        hass = MockHass()
        config = {
            Config.DISPLAY_UNIT: Defaults.DISPLAY_UNIT,
            Config.API_KEY: "test_key", # Example config
            Config.SOURCE_PRIORITY: [Source.NORDPOOL, Source.ENTSOE],
            Config.VAT: Defaults.VAT_RATE,
            Config.INCLUDE_VAT: Defaults.INCLUDE_VAT,
        }
        manager_instance = UnifiedPriceManager(
            hass=hass,
            area="SE1",
            currency="SEK",
            config=config,
        )
        # Manually set the exchange service on the instance after init, as it's lazy loaded
        manager_instance._exchange_service = auto_mock_core_dependencies["get_exchange_service"].return_value
        # Ensure processor also gets the mock service if needed by its init/process
        # This depends on DataProcessor implementation, assuming it might need it
        if hasattr(manager_instance._data_processor, '_exchange_service'):
             manager_instance._data_processor._exchange_service = manager_instance._exchange_service

        return manager_instance

    def test_init(self, manager, auto_mock_core_dependencies):
        """Test initialization sets attributes correctly."""
        # Core attributes
        assert manager.area == "SE1", f"Expected area 'SE1', got '{manager.area}'"
        assert manager.currency == "SEK", f"Expected currency 'SEK', got '{manager.currency}'"
        
        # Initial state
        assert manager._active_source is None, "Active source should be None on initialization"
        assert manager._attempted_sources == [], "Attempted sources should be empty on initialization"
        assert manager._fallback_sources == [], "Fallback sources should be empty on initialization"
        assert manager._using_cached_data is False, "using_cached_data should be False on initialization"
        assert manager._consecutive_failures == 0, "Consecutive failures should be 0 on initialization"
        
        # Dependencies
        assert manager._tz_service is auto_mock_core_dependencies["tz_service"].return_value, "TimezoneService not properly initialized"
        assert manager._fallback_manager is auto_mock_core_dependencies["fallback_manager"].return_value, "FallbackManager not properly initialized"
        assert manager._cache_manager is auto_mock_core_dependencies["cache_manager"].return_value, "CacheManager not properly initialized"
        assert manager._data_processor is auto_mock_core_dependencies["data_processor"].return_value, "DataProcessor not properly initialized"
        
        # Source configuration
        assert manager._source_priority == [Source.NORDPOOL, Source.ENTSOE], "Source priority not correctly initialized"
        assert len(manager._api_classes) == 2, f"Expected 2 API classes, got {len(manager._api_classes)}"

    @pytest.mark.asyncio
    async def test_fetch_data_success_first_source(self, manager, auto_mock_core_dependencies):
        """Test successful fetch using the primary source."""
        # Arrange: Mocks already configured for success by default fixture
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.update_cache
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallbacks should be called once"
        
        # Verify processor called with correct raw data
        mock_processor.assert_awaited_once_with(MOCK_SUCCESS_RESULT), \
            f"DataProcessor.process should be called with raw data, got {mock_processor.call_args}"
            
        # Verify cache updated with processed data
        mock_cache_update.assert_called_once_with(MOCK_PROCESSED_RESULT), \
            f"CacheManager.update_cache should be called with processed data, got {mock_cache_update.call_args}"
            
        # Cache get shouldn't be called on normal success
        mock_cache_get.assert_not_called(), "CacheManager.get_cached_data should not be called on successful fetch"
        
        # Check returned data
        assert result == MOCK_PROCESSED_RESULT, f"Expected processed result, got {json.dumps(result, indent=2)}"
        
        # Check manager state updates
        assert manager._active_source == Source.NORDPOOL, f"Active source should be NORDPOOL, got {manager._active_source}"
        assert manager._attempted_sources == [Source.NORDPOOL], f"Attempted sources should be [NORDPOOL], got {manager._attempted_sources}"
        assert manager._fallback_sources == [], f"Fallback sources should be empty, got {manager._fallback_sources}"
        assert manager._using_cached_data is False, f"using_cached_data should be False, got {manager._using_cached_data}"
        assert manager._consecutive_failures == 0, f"Consecutive failures should be 0, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_fetch_data_success_fallback_source(self, manager, auto_mock_core_dependencies):
        """Test successful fetch using a fallback source when primary fails."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.update_cache

        # Create realistic data for fallback success scenario
        fallback_success_result = {
            **MOCK_SUCCESS_RESULT,
            "data_source": Source.ENTSOE,
            "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
        }
        processed_fallback_result = {
            **MOCK_PROCESSED_RESULT,
            "source": Source.ENTSOE,
            "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
            "fallback_sources": [Source.NORDPOOL],
        }
        mock_fallback.return_value = fallback_success_result
        mock_processor.return_value = processed_fallback_result

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallbacks should be called once"
        
        # Verify processor called with fallback data
        mock_processor.assert_awaited_once_with(fallback_success_result), \
            f"DataProcessor.process should be called with fallback data, got {mock_processor.call_args}"
            
        # Verify cache updated with processed fallback data
        mock_cache_update.assert_called_once_with(processed_fallback_result), \
            f"CacheManager.update_cache should be called with processed fallback data, got {mock_cache_update.call_args}"
        
        # Check returned data
        assert result == processed_fallback_result, f"Expected processed fallback result, got {json.dumps(result, indent=2)}"
        
        # Check manager state updates
        assert manager._active_source == Source.ENTSOE, f"Active source should be ENTSOE, got {manager._active_source}"
        assert manager._attempted_sources == [Source.NORDPOOL, Source.ENTSOE], \
            f"Attempted sources incorrect: {manager._attempted_sources}"
        assert manager._fallback_sources == [Source.NORDPOOL], \
            f"Fallback sources should include failed NORDPOOL, got {manager._fallback_sources}"
        assert manager._using_cached_data is False, f"using_cached_data should be False, got {manager._using_cached_data}"
        assert manager._consecutive_failures == 0, f"Consecutive failures should be 0, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_fetch_data_failure_all_sources_no_cache(self, manager, auto_mock_core_dependencies):
        """Test failure when all sources fail and no cache is available - critical production scenario."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.update_cache

        mock_fallback.return_value = MOCK_FAILURE_RESULT # Simulate failure from FallbackManager
        mock_cache_get.return_value = None # No cache available
        # Processor will be called with the failure result to generate the empty structure
        mock_processor.return_value = MOCK_EMPTY_PROCESSED_RESULT

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallbacks should be called once"
        
        # Check cache was attempted with the correct TTL
        mock_cache_get.assert_called_once_with(max_age_minutes=Defaults.CACHE_TTL), \
            f"CacheManager.get_cached_data should be called with default TTL, got {mock_cache_get.call_args}"
        
        # Processor is called by _generate_empty_result which itself calls _process_result
        mock_processor.assert_awaited_once(), "DataProcessor.process should be called once"
        
        # Check result structure and content
        assert result == MOCK_EMPTY_PROCESSED_RESULT, \
            f"Expected empty processed result, got {json.dumps(result, indent=2)}"
        assert result.get("error"), "Error message should be present in result"
        assert not result.get("hourly_prices"), "hourly_prices should be empty"
        assert result.get("has_data") is False, "has_data should be False"
        
        # Cache should not be updated on failure
        mock_cache_update.assert_not_called(), "CacheManager.update_cache should not be called on failure"
        
        # Check manager state updates
        assert manager._active_source == "None", f"Active source should be 'None', got {manager._active_source}"
        assert manager._attempted_sources == [Source.NORDPOOL, Source.ENTSOE], \
            f"Attempted sources incorrect: {manager._attempted_sources}"
        assert manager._fallback_sources == [Source.NORDPOOL, Source.ENTSOE], \
            f"All sources should be in fallback_sources, got {manager._fallback_sources}"
        assert manager._using_cached_data is True, \
            f"using_cached_data should be True (though failed), got {manager._using_cached_data}"
        assert manager._consecutive_failures == 1, \
            f"Consecutive failures should be 1, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_fetch_data_failure_all_sources_uses_cache(self, manager, auto_mock_core_dependencies):
        """Test failure when all sources fail but valid cache is available - common fallback scenario."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.update_cache

        mock_fallback.return_value = MOCK_FAILURE_RESULT # Simulate failure
        mock_cache_get.return_value = MOCK_CACHED_RESULT # Provide cached data
        # Processor will be called with the cached data
        mock_processor.return_value = MOCK_CACHED_RESULT # Assume processor returns it as is (or re-processes)

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallbacks should be called once"
        
        # Check cache was attempted with the correct TTL
        mock_cache_get.assert_called_once_with(max_age_minutes=Defaults.CACHE_TTL), \
            f"CacheManager.get_cached_data should be called with default TTL, got {mock_cache_get.call_args}"
        
        # Processor will be called with the cached data
        mock_processor.assert_awaited_once(), "DataProcessor.process should be called once"
        
        # Check result structure and content
        assert result == MOCK_CACHED_RESULT, f"Expected cached result, got {json.dumps(result, indent=2)}"
        assert result["using_cached_data"] is True, "using_cached_data flag should be True"
        assert result.get("hourly_prices"), "hourly_prices should not be empty"
        
        # Cache not updated when using cache due to failure
        mock_cache_update.assert_not_called(), "CacheManager.update_cache should not be called when using cache"
        
        # Check manager state updates
        assert manager._active_source == "None", f"Active source should be 'None', got {manager._active_source}"
        assert manager._attempted_sources == [Source.NORDPOOL, Source.ENTSOE], \
            f"Attempted sources incorrect: {manager._attempted_sources}"
        assert manager._fallback_sources == [Source.NORDPOOL, Source.ENTSOE], \
            f"All sources should be in fallback_sources, got {manager._fallback_sources}"
        assert manager._using_cached_data is True, f"using_cached_data should be True, got {manager._using_cached_data}"
        assert manager._consecutive_failures == 1, f"Consecutive failures should be 1, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_rate_limiting_uses_cache(self, manager, auto_mock_core_dependencies):
        """Test that rate limiting prevents fetch and uses cache - prevents API abuse."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process

        # First call - successful fetch
        now_time = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now_time
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = MOCK_PROCESSED_RESULT
        await manager.fetch_data()
        
        # Reset mocks for second call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.return_value = MOCK_CACHED_RESULT # Make cache available
        # Assume processor returns cached data when processing cached input
        mock_processor.return_value = MOCK_CACHED_RESULT

        # Advance time slightly, but less than min interval (e.g., 3 minutes for a 5 minute interval)
        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act - Second call should use cache due to rate limiting
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_not_awaited(), "FallbackManager.fetch_with_fallbacks should not be called due to rate limiting"
        mock_cache_get.assert_called_once(), "CacheManager.get_cached_data should be called when rate limited"
        mock_processor.assert_awaited_once(), "DataProcessor.process should be called with cached data"
        
        # Check result uses cached data
        assert result == MOCK_CACHED_RESULT, f"Expected cached result, got {json.dumps(result, indent=2)}"
        assert result["using_cached_data"] is True, "using_cached_data flag should be True"

    @pytest.mark.asyncio
    async def test_rate_limiting_no_cache(self, manager, auto_mock_core_dependencies):
        """Test rate limiting when no cache is available - rare but important edge case."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process

        # First call - successful fetch
        now_time = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now_time
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = MOCK_PROCESSED_RESULT
        await manager.fetch_data()
        
        # Reset mocks for second call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        mock_cache_get.return_value = None # No cache
        
        # Prepare empty result for rate limited case
        expected_empty_result = {
            **MOCK_EMPTY_PROCESSED_RESULT,
            "error": "Rate limited, no cache available",
            "using_cached_data": True # This scenario implies cache was intended/checked
        }
        mock_processor.return_value = expected_empty_result

        # Advance time slightly, but less than min interval
        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act - Second call should try cache but find none
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_not_awaited(), "FallbackManager.fetch_with_fallbacks should not be called due to rate limiting"
        mock_cache_get.assert_called_once(), "CacheManager.get_cached_data should be called when rate limited"
        mock_processor.assert_awaited_once(), "DataProcessor.process should be called to generate empty result"
        
        # Check result is empty with rate limit error
        assert result == expected_empty_result, f"Expected empty result with rate limit error, got {json.dumps(result, indent=2)}"
        assert "Rate limited" in result.get("error", ""), "Error should mention rate limiting"
        assert result["using_cached_data"] is True, "using_cached_data flag should be True (though cache not found)"
        assert not result.get("hourly_prices"), "hourly_prices should be empty"

    @pytest.mark.asyncio
    async def test_force_fetch_bypasses_rate_limit(self, manager, auto_mock_core_dependencies):
        """Test that force=True bypasses rate limiting - critical for manual refresh requests."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process

        # First call - regular fetch
        now_time = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now_time
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = MOCK_PROCESSED_RESULT
        await manager.fetch_data()
        
        # Reset mocks for second call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        
        # Advance time slightly, but less than min interval
        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act - Second call with force=True
        result = await manager.fetch_data(force=True)

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallbacks should be called when forced"
        mock_processor.assert_awaited_once_with(MOCK_SUCCESS_RESULT), \
            "DataProcessor.process should be called with actual fetch result"
        
        # Check result is fresh data, not cached
        assert result == MOCK_PROCESSED_RESULT, f"Expected fresh processed result, got {json.dumps(result, indent=2)}"
        assert result["using_cached_data"] is False, "using_cached_data flag should be False when forced"

    @pytest.mark.asyncio
    async def test_fetch_data_failure_with_service_unavailable(self, manager, auto_mock_core_dependencies):
        """Test handling of real-world scenario where service is temporarily unavailable."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data
        
        # Simulate a service unavailable error (HTTP 503)
        from aiohttp import ClientResponseError, ClientResponse
        mock_response = MagicMock(spec=ClientResponse)
        mock_response.status = 503
        mock_response.reason = "Service Unavailable"
        service_error = ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=503,
            message="503, message='Service Unavailable'",
            headers={}
        )
        mock_fallback.side_effect = service_error
        
        # Configure processor to return empty result for failed fetch
        mock_processor.return_value = MOCK_EMPTY_PROCESSED_RESULT
        mock_cache_get.return_value = None # No cache
        
        # Act
        result = await manager.fetch_data()
        
        # Assert
        assert result is not None, "Result should not be None even on service error"
        assert "hourly_prices" in result, "Result should have hourly_prices structure even on service error"
        assert not result["hourly_prices"], f"hourly_prices should be empty on service error, got {result.get('hourly_prices')}"
        assert result["has_data"] is False, "has_data should be False on service error"
        assert "error" in result, "Error message should be present"
        assert "503" in str(result.get("error", "")), f"Error should mention HTTP status, got {result.get('error')}"
        assert "Service Unavailable" in str(result.get("error", "")), f"Error should mention reason, got {result.get('error')}"
        assert result["source"] == "None", f"Source should be None on error, got {result.get('source')}"
        
        # Critical real-world validation: source tracking should work
        assert "attempted_sources" in result, "attempted_sources should be present"
        assert len(result["attempted_sources"]) > 0, "attempted_sources should not be empty"
        assert "fallback_sources" in result, "fallback_sources should be present"
        
        # Verify retry mechanism setup
        assert manager._consecutive_failures == 1, "consecutive_failures should be incremented"

    @pytest.mark.asyncio
    async def test_fetch_data_with_malformed_api_response(self, manager, auto_mock_core_dependencies):
        """Test handling of malformed API response - real-world scenario with broken API."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data
        
        # Simulate success from API but with malformed data
        malformed_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            # Missing hourly_prices - malformed response
            "attempted_sources": [Source.NORDPOOL],
            "error": None,
        }
        mock_fallback.return_value = malformed_result
        
        # Handle malformed data in processor
        mock_processor.side_effect = KeyError("hourly_prices")
        mock_cache_get.return_value = None # No cache
        
        # Act
        try:
            result = await manager.fetch_data()
            
            # Test implementation's error handling
            assert result is not None, "Result should not be None on malformed data"
            assert "error" in result, "Error should be indicated on malformed data"
            assert "KeyError" in str(result.get("error", "")), f"Error should mention the specific error, got {result.get('error')}"
            assert "hourly_prices" in str(result.get("error", "")), f"Error should mention the missing key, got {result.get('error')}"
            assert not result.get("hourly_prices", {}), "hourly_prices should be empty or properly structured"
            assert result.get("has_data", True) is False, "has_data should be False on malformed data"
            
        except KeyError:
            # Implementation doesn't handle malformed data gracefully
            pytest.fail("UnifiedPriceManager should handle malformed API responses gracefully")

    @pytest.mark.asyncio
    async def test_fetch_data_with_out_of_bounds_prices(self, manager, auto_mock_core_dependencies):
        """Test handling of anomalous price values - real-world scenario of price spikes."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        
        # Normal result structure but with extreme prices
        extreme_price_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            "hourly_prices": {
                "2025-04-26T10:00:00+00:00": 9999.99,  # Extreme high price
                "2025-04-26T11:00:00+00:00": -500.0,   # Extreme negative price
                "2025-04-26T12:00:00+00:00": 2.5,      # Normal price
            },
            "attempted_sources": [Source.NORDPOOL],
            "error": None,
        }
        mock_fallback.return_value = extreme_price_result
        
        # Configure processor to pass through extreme prices
        # In real implementation, processor should validate but not clip these values
        extreme_processed_result = {
            **MOCK_PROCESSED_RESULT,
            "hourly_prices": {
                "2025-04-26T10:00:00+02:00": 9999.99,
                "2025-04-26T11:00:00+02:00": -500.0,
                "2025-04-26T12:00:00+02:00": 2.5,
            }
        }
        mock_processor.return_value = extreme_processed_result
        
        # Act
        result = await manager.fetch_data()
        
        # Assert - Extreme prices should be preserved, not clipped
        assert result["hourly_prices"]["2025-04-26T10:00:00+02:00"] == 9999.99, \
            f"Extreme high price should not be clipped, got {result['hourly_prices']['2025-04-26T10:00:00+02:00']}"
        assert result["hourly_prices"]["2025-04-26T11:00:00+02:00"] == -500.0, \
            f"Negative price should not be clipped, got {result['hourly_prices']['2025-04-26T11:00:00+02:00']}"
        
        # Both normal and extreme prices should be present
        assert len(result["hourly_prices"]) == 3, \
            f"All price points should be preserved, got {len(result['hourly_prices'])}"
        
        # Result should indicate successful fetch despite extreme prices
        assert result["has_data"] is True, "has_data should be True despite extreme prices"
        assert not result.get("error"), f"No error should be present for extreme prices, got {result.get('error')}"

    @pytest.mark.asyncio
    async def test_fetch_data_with_currency_conversion(self, manager, auto_mock_core_dependencies):
        """Test proper currency conversion in real-world scenarios with differing currencies."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_exchange_service = auto_mock_core_dependencies["get_exchange_service"].return_value
        
        # Create result with EUR as source currency but SEK as target
        eur_result = {
            "data_source": Source.ENTSOE,
            "area": "SE1",
            "currency": Currency.EUR,  # Source currency is EUR
            "hourly_prices": {
                "2025-04-26T10:00:00+00:00": 0.1,  # EUR prices
                "2025-04-26T11:00:00+00:00": 0.2,
            },
            "attempted_sources": [Source.ENTSOE],
            "error": None,
        }
        mock_fallback.return_value = eur_result
        
        # Configure exchange service to simulate conversion
        mock_exchange_service.convert_currency = AsyncMock(return_value=10.5)  # 1 EUR = 10.5 SEK
        
        # Expected processed result with converted currency
        converted_result = {
            **MOCK_PROCESSED_RESULT,
            "source": Source.ENTSOE,
            "source_currency": Currency.EUR,
            "target_currency": Currency.SEK,
            "hourly_prices": {
                "2025-04-26T10:00:00+02:00": 1.05,  # 0.1 EUR * 10.5 = 1.05 SEK
                "2025-04-26T11:00:00+02:00": 2.1,   # 0.2 EUR * 10.5 = 2.1 SEK
            },
            "exchange_rate": 10.5,
        }
        mock_processor.return_value = converted_result
        
        # Act
        result = await manager.fetch_data()
        
        # Assert
        assert result["source_currency"] == Currency.EUR, \
            f"Source currency should be EUR, got {result.get('source_currency')}"
        assert result["target_currency"] == Currency.SEK, \
            f"Target currency should be SEK, got {result.get('target_currency')}"
        assert "exchange_rate" in result, "Exchange rate should be included in result"
        assert result["exchange_rate"] == 10.5, f"Exchange rate should be 10.5, got {result.get('exchange_rate')}"
        
        # Check converted prices
        assert result["hourly_prices"]["2025-04-26T10:00:00+02:00"] == 1.05, \
            f"First hour price should be converted to 1.05 SEK, got {result['hourly_prices']['2025-04-26T10:00:00+02:00']}"
        assert result["hourly_prices"]["2025-04-26T11:00:00+02:00"] == 2.1, \
            f"Second hour price should be converted to 2.1 SEK, got {result['hourly_prices']['2025-04-26T11:00:00+02:00']}"

    @pytest.mark.asyncio  
    async def test_fetch_data_with_timezone_conversion(self, manager, auto_mock_core_dependencies):
        """Test correct timezone conversion - critical for international markets."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_tz_service = auto_mock_core_dependencies["tz_service"].return_value
        
        # Create result with UTC timestamps
        utc_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            "api_timezone": "UTC",
            "hourly_prices": {
                "2025-04-26T10:00:00+00:00": 1.0,  # UTC timestamps
                "2025-04-26T11:00:00+00:00": 2.0,
            },
            "attempted_sources": [Source.NORDPOOL],
            "error": None,
        }
        mock_fallback.return_value = utc_result
        
        # Configure timezone service
        mock_tz_service.get_area_timezone.return_value = "Europe/Stockholm"
        
        # Expected processed result with converted timezone
        converted_tz_result = {
            **MOCK_PROCESSED_RESULT,
            "source_timezone": "UTC",
            "target_timezone": "Europe/Stockholm",
            "hourly_prices": {
                "2025-04-26T12:00:00+02:00": 1.0,  # UTC+2 for Stockholm
                "2025-04-26T13:00:00+02:00": 2.0,
            }
        }
        mock_processor.return_value = converted_tz_result
        
        # Act
        result = await manager.fetch_data()
        
        # Assert
        assert "source_timezone" in result, "Source timezone should be included in result" 
        assert "target_timezone" in result, "Target timezone should be included in result"
        assert result["source_timezone"] == "UTC", f"Source timezone should be UTC, got {result.get('source_timezone')}"
        assert result["target_timezone"] == "Europe/Stockholm", \
            f"Target timezone should be Europe/Stockholm, got {result.get('target_timezone')}"
        
        # Check converted timestamps
        assert "2025-04-26T12:00:00+02:00" in result["hourly_prices"], \
            f"First hour should be converted to local time, got keys: {list(result['hourly_prices'].keys())}"
        assert "2025-04-26T13:00:00+02:00" in result["hourly_prices"], \
            f"Second hour should be converted to local time, got keys: {list(result['hourly_prices'].keys())}"

    @pytest.mark.asyncio
    async def test_consecutive_failures_backoff(self, manager, auto_mock_core_dependencies):
        """Test that consecutive failures implement backoff strategy - prevents API hammering."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_now = auto_mock_core_dependencies["now"]
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data
        
        # Configure for failure
        mock_fallback.return_value = MOCK_FAILURE_RESULT
        mock_processor.return_value = MOCK_EMPTY_PROCESSED_RESULT
        mock_cache_get.return_value = None  # No cache
        
        # First failure
        await manager.fetch_data()
        assert manager._consecutive_failures == 1, "First failure should set counter to 1"
        
        # Reset for second call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        
        # Advance time past the regular rate limit
        mock_now.return_value += timedelta(minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES + 1)
        
        # Second failure
        await manager.fetch_data()
        assert manager._consecutive_failures == 2, "Second failure should increment counter to 2"
        
        # Reset for third call
        mock_fallback.reset_mock() 
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        
        # Advance time but not enough for backoff
        mock_now.return_value += timedelta(minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES + 1)
        
        # Attempt third fetch - should be rate limited due to backoff
        result = await manager.fetch_data()
        
        # API call should be skipped due to backoff
        mock_fallback.assert_not_awaited(), "API should not be called during backoff period"
        
        # Result should indicate backoff
        assert "error" in result, "Error message should be present"
        assert "backoff" in str(result.get("error", "")).lower(), \
            f"Error should mention backoff strategy, got {result.get('error')}"
        
        # Reset for forced call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        
        # Force fetch should work despite backoff
        await manager.fetch_data(force=True)
        mock_fallback.assert_awaited_once(), "Forced fetch should bypass backoff"