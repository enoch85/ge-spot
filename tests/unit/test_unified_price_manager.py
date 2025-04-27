#!/usr/bin/env python3
"""Tests for the UnifiedPriceManager functionality."""
import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock, patch, AsyncMock, call # Added call
from datetime import datetime, timedelta, timezone
import pytest

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.coordinator.unified_price_manager import UnifiedPriceManager
from scripts.tests.mocks.hass import MockHass
from custom_components.ge_spot.const.sources import Source # Added
from custom_components.ge_spot.const.defaults import Defaults # Added
from custom_components.ge_spot.const.network import Network # Added
from custom_components.ge_spot.const.config import Config # Added import

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
    """Automatically mock core dependencies used by UnifiedPriceManager.""" # Removed stray backslash
    # Patch the global rate limiting dictionary to isolate tests
    with patch('custom_components.ge_spot.coordinator.unified_price_manager._LAST_FETCH_TIME', new_callable=dict) as mock_last_fetch_time, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.FallbackManager', new_callable=MagicMock) as mock_fallback_manager, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.CacheManager', new_callable=MagicMock) as mock_cache_manager, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.DataProcessor', new_callable=MagicMock) as mock_data_processor, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.TimezoneService', new_callable=MagicMock) as mock_tz_service, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.get_exchange_service', new_callable=AsyncMock) as mock_get_exchange_service, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.dt_util.now') as mock_now, \
         patch('custom_components.ge_spot.coordinator.unified_price_manager.async_get_clientsession') as mock_get_session, \
         patch('custom_components.ge_spot.api.get_sources_for_region') as mock_get_sources:

        # Configure default return values for mocks
        mock_get_sources.return_value = [Source.NORDPOOL, Source.ENTSOE]
        mock_fallback_manager.return_value.fetch_with_fallbacks = AsyncMock(return_value=MOCK_SUCCESS_RESULT)
        mock_cache_manager.return_value.get_cached_data = MagicMock(return_value=None)
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
    """Test the UnifiedPriceManager class.""" # Removed stray backslash

    @pytest.fixture
    def manager(self, auto_mock_core_dependencies):
        """Provides an initialized UnifiedPriceManager instance for tests.""" # Removed stray backslash
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
        """Test initialization sets attributes correctly.""" # Removed stray backslash
        assert manager.area == "SE1"
        assert manager.currency == "SEK"
        assert manager._active_source is None
        assert manager._attempted_sources == []
        assert manager._fallback_sources == []
        assert manager._using_cached_data is False
        assert manager._consecutive_failures == 0
        assert manager._tz_service is auto_mock_core_dependencies["tz_service"].return_value
        assert manager._fallback_manager is auto_mock_core_dependencies["fallback_manager"].return_value
        assert manager._cache_manager is auto_mock_core_dependencies["cache_manager"].return_value
        assert manager._data_processor is auto_mock_core_dependencies["data_processor"].return_value
        # Check source priority was configured
        assert manager._source_priority == [Source.NORDPOOL, Source.ENTSOE]
        assert len(manager._api_classes) == 2 # NordpoolAPI, EntsoeAPI

    @pytest.mark.asyncio
    async def test_fetch_data_success_first_source(self, manager, auto_mock_core_dependencies):
        """Test successful fetch using the primary source.""" # Removed stray backslash
        # Arrange: Mocks already configured for success by default fixture
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.update_cache
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_cached_data

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_awaited_once() # Check FallbackManager was called
        mock_processor.assert_awaited_once_with(MOCK_SUCCESS_RESULT) # Check processor called with raw data
        mock_cache_update.assert_called_once_with(MOCK_PROCESSED_RESULT) # Check cache updated with processed data
        mock_cache_get.assert_not_called() # Cache get shouldn't be called on normal success
        assert result == MOCK_PROCESSED_RESULT # Final result is the processed data
        assert manager._active_source == Source.NORDPOOL
        assert manager._attempted_sources == [Source.NORDPOOL]
        assert manager._fallback_sources == []
        assert manager._using_cached_data is False
        assert manager._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_fetch_data_success_fallback_source(self, manager, auto_mock_core_dependencies):
        """Test successful fetch using a fallback source.""" # Removed stray backslash
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.update_cache

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
        mock_fallback.assert_awaited_once()
        mock_processor.assert_awaited_once_with(fallback_success_result)
        mock_cache_update.assert_called_once_with(processed_fallback_result)
        assert result == processed_fallback_result
        assert manager._active_source == Source.ENTSOE
        assert manager._attempted_sources == [Source.NORDPOOL, Source.ENTSOE]
        assert manager._fallback_sources == [Source.NORDPOOL] # Nordpool was attempted and failed
        assert manager._using_cached_data is False
        assert manager._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_fetch_data_failure_all_sources_no_cache(self, manager, auto_mock_core_dependencies):
        """Test failure when all sources fail and no cache is available.""" # Removed stray backslash
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
        mock_fallback.assert_awaited_once()
        # Check cache was attempted with the correct TTL
        mock_cache_get.assert_called_once_with(max_age_minutes=Defaults.CACHE_TTL)
        # Processor is called by _generate_empty_result which itself calls _process_result
        mock_processor.assert_awaited_once()
        # Check the input to the processor was the generated empty structure from _generate_empty_result
        # (or the MOCK_FAILURE_RESULT before it gets processed into empty) - depends on implementation detail.
        # Let's check the final output is the processed empty result.
        assert result == MOCK_EMPTY_PROCESSED_RESULT
        mock_cache_update.assert_not_called() # Cache should not be updated on failure
        assert manager._active_source == "None"
        assert manager._attempted_sources == [Source.NORDPOOL, Source.ENTSOE]
        assert manager._fallback_sources == [Source.NORDPOOL, Source.ENTSOE] # All attempted sources are fallbacks
        assert manager._using_cached_data is True # Intended to use cache, but failed
        assert manager._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_fetch_data_failure_all_sources_uses_cache(self, manager, auto_mock_core_dependencies):
        """Test failure when all sources fail but valid cache is available.""" # Removed stray backslash
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
        mock_fallback.assert_awaited_once()
        # Check cache was attempted with the correct TTL
        mock_cache_get.assert_called_once_with(max_age_minutes=Defaults.CACHE_TTL)
        # Processor will be called with the cached data
        # Check the input structure carefully based on implementation
        # For now, check it was called
        mock_processor.assert_awaited_once()
        # Check the final result is the (potentially re-processed) cached data
        assert result == MOCK_CACHED_RESULT
        assert result["using_cached_data"] is True # Verify flag
        mock_cache_update.assert_not_called() # Cache not updated when using cache due to failure
        assert manager._active_source == "None" # No active source fetched
        assert manager._attempted_sources == [Source.NORDPOOL, Source.ENTSOE]
        assert manager._fallback_sources == [Source.NORDPOOL, Source.ENTSOE]
        assert manager._using_cached_data is True
        assert manager._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_rate_limiting_uses_cache(self, manager, auto_mock_core_dependencies):
        """Test that rate limiting prevents fetch and uses cache.""" # Removed stray backslash
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
        mock_fallback.assert_awaited_once()
        mock_processor.assert_awaited_once_with(MOCK_SUCCESS_RESULT)

        # Second call - within rate limit interval
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.return_value = MOCK_CACHED_RESULT # Make cache available
        # Assume processor returns cached data when processing cached input
        mock_processor.return_value = MOCK_CACHED_RESULT

        # Advance time slightly, but less than min interval
        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_not_awaited() # Fetch should not happen
        mock_cache_get.assert_called_once() # Cache should be checked
        # Processor called with the cached data
        # Check the input structure carefully based on implementation
        # For now, check it was called
        mock_processor.assert_awaited_once()
        assert result == MOCK_CACHED_RESULT # Should return cached data
        assert result["using_cached_data"] is True

    @pytest.mark.asyncio
    async def test_rate_limiting_no_cache(self, manager, auto_mock_core_dependencies):
        """Test rate limiting when no cache is available.""" # Removed stray backslash
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
        mock_fallback.assert_awaited_once() # Verify first fetch happened

        # Second call - within rate limit interval, no cache
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock() # Reset cache mock before the second call
        mock_cache_get.return_value = None # No cache
        # Processor will be called by _generate_empty_result
        # Set up the mock processor to return the specific empty result for this test
        expected_empty_result = {
            **MOCK_EMPTY_PROCESSED_RESULT, # Start with the base empty result
            "error": "Rate limited, no cache available", # Set the expected error
            "using_cached_data": True # This scenario implies cache was intended/checked
        }
        mock_processor.return_value = expected_empty_result

        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_not_awaited() # Fetch should not happen
        mock_cache_get.assert_called_once() # Cache checked exactly once for this call

        # Check that the processor was called (via _generate_empty_result -> _process_result)
        # The input to the processor should contain the specific error message
        # We can check the call arguments if needed, but let's first check the final result
        mock_processor.assert_awaited_once()

        # Assert the final result matches the specific empty result we set the mock to return
        assert result == expected_empty_result
        assert "Rate limited" in result.get("error", "") # Verify the error message is correct in the final output
        assert result["using_cached_data"] is True # Verify the cache flag


    @pytest.mark.asyncio
    async def test_force_fetch_bypasses_rate_limit(self, manager, auto_mock_core_dependencies):
        """Test that force=True bypasses rate limiting.""" # Removed stray backslash
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallbacks
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process

        # First call
        now_time = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        mock_now.return_value = now_time
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = MOCK_PROCESSED_RESULT
        await manager.fetch_data()
        mock_fallback.assert_awaited_once()

        # Second call - within interval, but forced
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act
        result = await manager.fetch_data(force=True)

        # Assert
        mock_fallback.assert_awaited_once() # Fetch SHOULD happen
        mock_processor.assert_awaited_once_with(MOCK_SUCCESS_RESULT)
        assert result == MOCK_PROCESSED_RESULT

    # Remove or adapt old tests that are now covered or irrelevant
    # - test_fetch_data_failure (replaced by more specific failure tests)
    # - test_process_result (processing is tested implicitly in other tests)
    # - test_fetch_with_tomorrow_data (handled by FallbackManager/DataProcessor, not directly here)

# Keep this structure if running tests directly
# if __name__ == \"__main__\":
#     pytest.main([__file__])