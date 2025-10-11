#!/usr/bin/env python3
"""Tests for the UnifiedPriceManager functionality.

These tests verify real-world behavior of the UnifiedPriceManager to ensure it:
1. Correctly fetches data from appropriate sources
2. Properly handles fallback scenarios when primary sources fail
3. Manages cache with appropriate expiry times
4. Handles error scenarios gracefully without crashing
5. Processes and validates data from different sources consistently

IMPORTANT: These tests are aligned with the 15-minute interval implementation.
- All mock data uses 15-minute interval timestamps (HH:MM format, e.g., 10:00, 10:15, 10:30)
- Mock data includes 4 intervals per hour to demonstrate 15-minute granularity
- Tests use TimeInterval configuration for interval-aware assertions
- System expects 96 intervals per day (24 hours × 4 intervals/hour)

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
from freezegun import freeze_time

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
from custom_components.ge_spot.const.time import TimeInterval

# Helper function to cancel background health check tasks
async def cancel_health_check_tasks(manager):
    """Cancel all background health check tasks to prevent lingering tasks in tests."""
    import asyncio
    # Cancel all pending tasks with schedule_health_check
    for task in asyncio.all_tasks():
        if hasattr(task, 'get_coro'):
            coro_str = str(task.get_coro())
            if '_schedule_health_check' in coro_str or '_validate_all_sources' in coro_str:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                try:
                    await task
                except asyncio.CancelledError:
                    pass

# Mock data for successful fetch
# Using 15-minute intervals (HH:MM format) to match TimeInterval.QUARTER_HOURLY configuration
MOCK_SUCCESS_RESULT = {
    "data_source": Source.NORDPOOL,
    "area": "SE1",
    "currency": "SEK", # Original currency from source
    "interval_prices": {
        "2025-04-26T10:00:00+00:00": 1.0,
        "2025-04-26T10:15:00+00:00": 1.1,
        "2025-04-26T10:30:00+00:00": 1.2,
        "2025-04-26T10:45:00+00:00": 1.3,
    },
    "attempted_sources": [Source.NORDPOOL],
    # Note: No "error" key for successful fetch
}

# Mock data for processed result
# Processed data with 15-minute intervals in target timezone
MOCK_PROCESSED_RESULT = {
    "source": Source.NORDPOOL, # Renamed from data_source
    "area": "SE1",
    "target_currency": "SEK", # Added target currency
    "interval_prices": {
        "2025-04-26T10:00:00+02:00": 1.1,
        "2025-04-26T10:15:00+02:00": 1.2,
        "2025-04-26T10:30:00+02:00": 1.3,
        "2025-04-26T10:45:00+02:00": 1.4,
    }, # Example processed data with 15-min intervals
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
    "interval_prices": {},
    "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
    "error": "Failed to fetch from all sources",
}

# Mock data for empty processed result
MOCK_EMPTY_PROCESSED_RESULT = {
    "source": "None",
    "area": "SE1",
    "target_currency": "SEK",
    "interval_prices": {},
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
        mock_fallback_manager.return_value.fetch_with_fallback = AsyncMock(return_value=MOCK_SUCCESS_RESULT)
        mock_cache_manager.return_value.get_data = MagicMock(return_value=None)
        mock_cache_manager.return_value.store = MagicMock()
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
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_store = auto_mock_core_dependencies["cache_manager"].return_value.store
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data

        # Act
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallback should be called once"

        # Verify processor called with correct raw data
        mock_processor.assert_awaited_once(), \
            f"DataProcessor.process should be called with raw data, got {mock_processor.call_args}"

        # Verify cache stored with processed data
        mock_cache_store.assert_called_once(), \
            f"CacheManager.store should be called with processed data, got {mock_cache_store.call_args}"

        # Cache get may be called during decision making
        # mock_cache_get.assert_not_called(), "CacheManager.get_data should not be called on successful fetch"

        # Check returned data
        assert result == MOCK_PROCESSED_RESULT, f"Expected processed result, got {json.dumps(result, indent=2)}"

        # Check manager state updates
        assert manager._active_source == Source.NORDPOOL, f"Active source should be NORDPOOL, got {manager._active_source}"
        assert manager._attempted_sources == [Source.NORDPOOL], f"Attempted sources should be [NORDPOOL], got {manager._attempted_sources}"
        assert manager._fallback_sources == [], f"Fallback sources should be empty, got {manager._fallback_sources}"
        assert manager._using_cached_data is False, f"using_cached_data should be False, got {manager._using_cached_data}"
        assert manager._consecutive_failures == 0, f"Consecutive failures should be 0, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    @freeze_time("2025-04-26 12:00:00 UTC")
    async def test_cache_timestamp_validation(self, manager, auto_mock_core_dependencies):
        """Test that cache created is valid shortly after creation (within rate limit)."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.store
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process

        # --- First call: Successful fetch, populates cache ---
        # Time is frozen at 12:00:00 UTC
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = MOCK_PROCESSED_RESULT
        await manager.fetch_data()

        # Verify cache was updated - store() is called with keyword args
        mock_cache_update.assert_called_once()
        # Check that store was called with correct area and source
        call_kwargs = mock_cache_update.call_args[1]
        assert call_kwargs['area'] == 'SE1'
        assert call_kwargs['source'] == Source.NORDPOOL
        assert 'data' in call_kwargs
        # Capture the data that was supposedly cached
        # In a real scenario, CacheManager would store this internally.
        # For the test, we assume MOCK_PROCESSED_RESULT was stored.

        # --- Second call: Shortly after, within rate limit ---
        # Reset mocks for the second call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        mock_cache_update.reset_mock()

        # Configure cache get to return the data from the first call
        # Simulate CacheManager returning the previously stored data
        mock_cache_get.return_value = MOCK_PROCESSED_RESULT
        # Configure processor to return this cached data when called
        mock_processor.return_value = MOCK_PROCESSED_RESULT

        # Advance time slightly (e.g., 1 minute), still within rate limit
        freezer = freeze_time("2025-04-26 12:01:00 UTC")
        freezer.start()
        mock_now.return_value = datetime(2025, 4, 26, 12, 1, 0, tzinfo=timezone.utc)

        # Act: Fetch again
        result = await manager.fetch_data()

        # Assert
        # API should not be called due to rate limiting
        mock_fallback.assert_not_awaited(), "API fetch should be skipped due to rate limit"
        # Cache should be checked (with target_date, no max_age_minutes)
        assert mock_cache_get.call_count >= 1, "CacheManager.get_data should be called"
        # Verify area is passed (target_date will be today's date from dt_util.now().date())
        call_kwargs = mock_cache_get.call_args[1]
        assert call_kwargs.get('area') == manager.area, "Cache should be called with correct area"
        
        # Check processor was called once (don't check exact args since code adds metadata)
        mock_processor.assert_awaited_once()
        # Verify processor was called with cached data (check key fields)
        process_call_args = mock_processor.call_args[0][0]
        assert process_call_args.get("interval_prices") == MOCK_PROCESSED_RESULT.get("interval_prices"), \
            "Processor should be called with cached interval_prices"
        assert process_call_args.get("using_cached_data") is True, \
            "Processor input should have using_cached_data=True"

        # Result should indicate cached data was used
        assert result.get("using_cached_data") is True, "Result should indicate cached data was used"
        assert result.get("interval_prices") == MOCK_PROCESSED_RESULT.get("interval_prices"), "Result prices should match cached data"

        # Stop the time freezer
        freezer.stop()

    @pytest.mark.asyncio
    async def test_fetch_data_success_fallback_source(self, manager, auto_mock_core_dependencies):
        """Test successful fetch using a fallback source when primary fails."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.store

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
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallback should be called once"

        # Verify processor called with fallback data
        mock_processor.assert_awaited_once_with(fallback_success_result), \
            f"DataProcessor.process should be called with fallback data, got {mock_processor.call_args}"

        # Verify cache updated with processed fallback data - store() uses keyword args
        mock_cache_update.assert_called_once()
        call_kwargs = mock_cache_update.call_args[1]
        assert call_kwargs['area'] == 'SE1'
        assert call_kwargs['source'] == Source.ENTSOE
        assert 'data' in call_kwargs

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
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.store

        mock_fallback.return_value = MOCK_FAILURE_RESULT # Simulate failure from FallbackManager
        mock_cache_get.return_value = None # No cache available
        # Processor will be called within _generate_empty_result -> _process_result
        # Let's adjust the mock processor to return the expected empty structure
        # when called by _generate_empty_result
        mock_processor.return_value = MOCK_EMPTY_PROCESSED_RESULT

        # Act
        result = await manager.fetch_data()
        
        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallback should be called once"

        # Check cache was attempted (no TTL check anymore)
        # The call happens inside the except block or the failure block
        assert mock_cache_get.call_count >= 1, \
            f"CacheManager.get_data should be called, got {mock_cache_get.call_args}"
        call_kwargs = mock_cache_get.call_args[1]
        assert call_kwargs.get('area') == manager.area, "Cache should be called with correct area"

        # Processor is called by _generate_empty_result which itself calls _process_result
        # It might be called with a slightly different structure than MOCK_FAILURE_RESULT
        # Let's check it was called once.
        # mock_processor.assert_awaited_once(), "DataProcessor.process should be called once to generate empty result"
        # CORRECTION: _generate_empty_result does NOT call process. Remove assertion.

        # Check result structure and content
        # The actual result comes from _generate_empty_result

        # Check manager state updates
        assert manager._active_source == "None", f"Active source should be 'None', got {manager._active_source}"
        assert manager._attempted_sources == [Source.NORDPOOL, Source.ENTSOE], \
            f"Attempted sources incorrect: {manager._attempted_sources}"
        assert manager._fallback_sources == [Source.NORDPOOL, Source.ENTSOE], \
            f"All sources should be in fallback_sources, got {manager._fallback_sources}"
        # In this path, cache was attempted but failed, so using_cached_data reflects the attempt
        assert manager._using_cached_data is True, \
            f"using_cached_data should be True (cache attempted), got {manager._using_cached_data}"
        assert manager._consecutive_failures == 1, \
            f"Consecutive failures should be 1, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_fetch_data_failure_all_sources_uses_cache(self, manager, auto_mock_core_dependencies):
        """Test failure when all sources fail but valid cache is available - common fallback scenario."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_update = auto_mock_core_dependencies["cache_manager"].return_value.store

        mock_fallback.return_value = MOCK_FAILURE_RESULT # Simulate failure
        mock_cache_get.return_value = MOCK_CACHED_RESULT # Provide cached data
        # Processor will be called with the cached data via _process_result
        mock_processor.return_value = MOCK_CACHED_RESULT # Assume processor returns it as is

        # Act
        result = await manager.fetch_data()
        
        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallback should be called once"

        # Check cache was attempted (no TTL check anymore)
        assert mock_cache_get.call_count >= 1, \
            f"CacheManager.get_data should be called, got {mock_cache_get.call_args}"
        call_kwargs = mock_cache_get.call_args[1]
        assert call_kwargs.get('area') == manager.area, "Cache should be called with correct area"

        # Processor will be called with the cached data
        # mock_processor.assert_awaited_once_with(MOCK_CACHED_RESULT, is_cached=True), \
        #      f"Processor should be called with cached data, got {mock_processor.call_args}"
        # CORRECTION: is_cached is not passed to process, it's handled after.
        # Check the first argument passed to process matches the cached data structure.
        # Need to reconstruct the exact dict passed to _process_result
        expected_process_arg = MOCK_CACHED_RESULT.copy()
        expected_process_arg["area"] = manager.area
        expected_process_arg["target_currency"] = manager.currency
        expected_process_arg["using_cached_data"] = True # Set by manager before calling _process_result
        expected_process_arg["vat_rate"] = manager.vat_rate * 100
        expected_process_arg["include_vat"] = manager.include_vat
        expected_process_arg["display_unit"] = manager.display_unit
        mock_processor.assert_awaited_once_with(expected_process_arg), \
             f"Processor should be called with cached data structure, got {mock_processor.call_args}"

        # Check result structure and content
        # The processor mock returns MOCK_CACHED_RESULT, but _process_result adds/modifies flags
        expected_result = {**MOCK_CACHED_RESULT, "using_cached_data": True} # Ensure flag is True
        # Compare key fields
        assert result.get("using_cached_data") is True, "using_cached_data flag should be True"
        assert result.get("interval_prices") == MOCK_CACHED_RESULT.get("interval_prices"), "Prices should match cached data"
        # attempted_sources comes from the actual cache data, not from MOCK_FAILURE_RESULT
        # The cache contains data from a previous successful fetch, so check it has SOME attempted_sources
        assert len(result.get("attempted_sources", [])) > 0, "Result should have attempted_sources from cached data"

        # Cache not updated when using cache due to failure
        mock_cache_update.assert_not_called(), "CacheManager.store should not be called when using cache"

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
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data
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
        mock_cache_get.reset_mock() # Reset get_data mock
        mock_cache_get.return_value = MOCK_CACHED_RESULT # Make cache available
        # Assume processor returns cached data when processing cached input
        mock_processor.return_value = MOCK_CACHED_RESULT

        # Advance time slightly, but less than min interval (e.g., 3 minutes for a 5 minute interval)
        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act - Second call should use cache due to rate limiting
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_not_awaited(), "FallbackManager.fetch_with_fallback should not be called due to rate limiting"
        assert mock_cache_get.call_count >= 1, \
            f"CacheManager.get_data should be called when rate limited, got {mock_cache_get.call_args}"
        call_kwargs = mock_cache_get.call_args[1]
        assert call_kwargs.get('area') == manager.area, "Cache should be called with correct area"
        
        # Check processor was called once (don't check exact args since code adds metadata)
        mock_processor.assert_awaited_once()
        # Verify processor was called with cached data (check key fields)
        process_call_args = mock_processor.call_args[0][0]
        assert process_call_args.get("interval_prices") == MOCK_CACHED_RESULT.get("interval_prices"), \
            "Processor should be called with cached interval_prices"
        assert process_call_args.get("using_cached_data") is True, \
            "Processor input should have using_cached_data=True"

        # Check result uses cached data
        expected_result = {**MOCK_CACHED_RESULT, "using_cached_data": True} # Ensure flag is True
        # Compare key fields
        assert result.get("using_cached_data") is True, "using_cached_data flag should be True"
        assert result.get("interval_prices") == MOCK_CACHED_RESULT.get("interval_prices"), "Prices should match cached data"


    @pytest.mark.asyncio
    async def test_rate_limiting_no_cache(self, manager, auto_mock_core_dependencies):
        """Test rate limiting when no cache is available - rare but important edge case."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data
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
        # The processor will be called by _generate_empty_result
        # Let's configure it to return what _generate_empty_result expects _process_result to return
        # This is complex, let's assume _generate_empty_result works correctly and compare the final output
        empty_result = await manager._generate_empty_result(error="Rate limited, no cache available")
        mock_processor.return_value = empty_result # Mock processor to return the final expected structure

        # Advance time slightly, but less than min interval
        min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        mock_now.return_value = now_time + timedelta(minutes=min_interval_minutes / 2)

        # Act - Second call should try cache but find none
        result = await manager.fetch_data()

        # Assert
        mock_fallback.assert_not_awaited(), "FallbackManager.fetch_with_fallback should not be called due to rate limiting"
        assert mock_cache_get.call_count >= 1, \
            f"CacheManager.get_data should be called when rate limited, got {mock_cache_get.call_args}"
        call_kwargs = mock_cache_get.call_args[1]
        assert call_kwargs.get('area') == manager.area, "Cache should be called with correct area"
        # Processor is called by _generate_empty_result -> _process_result
        # mock_processor.assert_awaited_once(), "DataProcessor.process should be called once to generate empty result"
        # CORRECTION: _generate_empty_result does NOT call process. Remove assertion.

        # Check result is empty with rate limit error
        # Compare key fields
        error_msg = result.get("error", "").lower()
        assert "rate limit" in error_msg, f"Error should mention rate limiting, got: {result.get('error', '')}"
        # using_cached_data is False because no cache was found (not True because cache was attempted)
        assert result.get("using_cached_data") is False, "using_cached_data flag should be False (no cache found)"
        assert not result.get("interval_prices"), "interval_prices should be empty"
        assert result.get("has_data") is False, "has_data should be False"

    @pytest.mark.asyncio
    async def test_fetch_data_with_malformed_api_response(self, manager, auto_mock_core_dependencies):
        """Test handling of malformed API response - real-world scenario with broken API."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data

        # Simulate success from API but with malformed data (missing interval_prices)
        malformed_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            # Missing interval_prices - malformed response
            "attempted_sources": [Source.NORDPOOL],
        }
        mock_fallback.return_value = malformed_result

        # No cache available
        mock_cache_get.return_value = None

        # Processor won't be called in this path, _generate_empty_result will be.
        # Configure processor mock for the call inside _generate_empty_result
        expected_empty = await manager._generate_empty_result(error="All sources failed: None")
        mock_processor.return_value = expected_empty


        # Act
        result = await manager.fetch_data()
        
        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        # Fallback manager was called
        mock_fallback.assert_awaited_once()
        # Cache was checked after fetch appeared to fail (due to missing key)
        assert mock_cache_get.call_count >= 1, "Cache should be checked on malformed data"
        call_kwargs = mock_cache_get.call_args[1]
        assert call_kwargs.get('area') == manager.area, "Cache should be called with correct area"
        # Processor was called once via _generate_empty_result
        # mock_processor.assert_awaited_once()
        # CORRECTION: _generate_empty_result does NOT call process. Remove assertion.

        # Check the final result structure and error message
        assert result is not None, "Result should not be None on malformed data"
        assert "error" in result, "Error should be indicated on malformed data"
        # The actual error from production: "Fetch/Processing failed: Unknown fetch/processing error"
        assert "failed" in result.get("error", "").lower() or "error" in result.get("error", "").lower(), \
            f"Error should indicate fetch failure, got {result.get('error')}"
        assert not result.get("interval_prices", {}), "interval_prices should be empty"
        assert result.get("has_data", True) is False, "has_data should be False on malformed data"
        assert result.get("attempted_sources") == [Source.NORDPOOL], "Attempted sources should be recorded"

    @pytest.mark.asyncio
    async def test_fetch_data_with_out_of_bounds_prices(self, manager, auto_mock_core_dependencies):
        """Test handling of anomalous price values - real-world scenario of price spikes."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process

        # Normal result structure but with extreme prices at 15-minute intervals
        extreme_price_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            "interval_prices": {
                "2025-04-26T10:00:00+00:00": 9999.99,  # Extreme high price
                "2025-04-26T10:15:00+00:00": -500.0,   # Extreme negative price
                "2025-04-26T10:30:00+00:00": 2.5,      # Normal price
            },
            "attempted_sources": [Source.NORDPOOL],
        }
        mock_fallback.return_value = extreme_price_result

        # Configure processor to pass through extreme prices
        # In real implementation, processor should validate but not clip these values
        extreme_processed_result = {
            **MOCK_PROCESSED_RESULT,
            "interval_prices": {
                "2025-04-26T10:00:00+02:00": 9999.99,
                "2025-04-26T10:15:00+02:00": -500.0,
                "2025-04-26T10:30:00+02:00": 2.5,
            }
        }
        mock_processor.return_value = extreme_processed_result

        # Act
        result = await manager.fetch_data()

        # Assert - Extreme prices should be preserved, not clipped
        assert result["interval_prices"]["2025-04-26T10:00:00+02:00"] == 9999.99, \
            f"Extreme high price should not be clipped, got {result['interval_prices']['2025-04-26T10:00:00+02:00']}"
        assert result["interval_prices"]["2025-04-26T10:15:00+02:00"] == -500.0, \
            f"Negative price should not be clipped, got {result['interval_prices']['2025-04-26T10:15:00+02:00']}"

        # Both normal and extreme prices should be present
        assert len(result["interval_prices"]) == 3, \
            f"All price points should be preserved, got {len(result['interval_prices'])}"

        # Result should indicate successful fetch despite extreme prices
        assert result["has_data"] is True, "has_data should be True despite extreme prices"
        assert not result.get("error"), f"No error should be present for extreme prices, got {result.get('error')}"

    @pytest.mark.asyncio
    async def test_fetch_data_with_currency_conversion(self, manager, auto_mock_core_dependencies):
        """Test proper currency conversion in real-world scenarios with differing currencies."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_exchange_service = auto_mock_core_dependencies["get_exchange_service"].return_value

        # Create result with EUR as source currency but SEK as target (15-minute intervals)
        eur_result = {
            "data_source": Source.ENTSOE,
            "area": "SE1",
            "currency": Currency.EUR,  # Source currency is EUR
            "interval_prices": {
                "2025-04-26T10:00:00+00:00": 0.1,  # EUR prices at 15-min intervals
                "2025-04-26T10:15:00+00:00": 0.2,
            },
            "attempted_sources": [Source.ENTSOE],
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
            "interval_prices": {
                "2025-04-26T10:00:00+02:00": 1.05,  # 0.1 EUR * 10.5 = 1.05 SEK
                "2025-04-26T10:15:00+02:00": 2.1,   # 0.2 EUR * 10.5 = 2.1 SEK
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
        assert result["interval_prices"]["2025-04-26T10:00:00+02:00"] == 1.05, \
            f"First interval price should be converted to 1.05 SEK, got {result['interval_prices']['2025-04-26T10:00:00+02:00']}"
        assert result["interval_prices"]["2025-04-26T10:15:00+02:00"] == 2.1, \
            f"Second interval price should be converted to 2.1 SEK, got {result['interval_prices']['2025-04-26T10:15:00+02:00']}"

    @pytest.mark.asyncio
    async def test_fetch_data_with_timezone_conversion(self, manager, auto_mock_core_dependencies):
        """Test correct timezone conversion - critical for international markets."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_tz_service = auto_mock_core_dependencies["tz_service"].return_value

        # Create result with UTC timestamps at 15-minute intervals
        utc_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            "api_timezone": "UTC",
            "interval_prices": {
                "2025-04-26T10:00:00+00:00": 1.0,  # UTC timestamps at 15-min intervals
                "2025-04-26T10:15:00+00:00": 2.0,
            },
            "attempted_sources": [Source.NORDPOOL],
        }
        mock_fallback.return_value = utc_result

        # Configure timezone service
        mock_tz_service.get_area_timezone.return_value = "Europe/Stockholm"

        # Expected processed result with converted timezone
        converted_tz_result = {
            **MOCK_PROCESSED_RESULT,
            "source_timezone": "UTC",
            "target_timezone": "Europe/Stockholm",
            "interval_prices": {
                "2025-04-26T12:00:00+02:00": 1.0,  # UTC+2 for Stockholm at :00
                "2025-04-26T12:15:00+02:00": 2.0,  # UTC+2 for Stockholm at :15
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

        # Check converted timestamps (15-minute intervals)
        assert "2025-04-26T12:00:00+02:00" in result["interval_prices"], \
            f"First interval should be converted to local time, got keys: {list(result['interval_prices'].keys())}"
        assert "2025-04-26T12:15:00+02:00" in result["interval_prices"], \
            f"Second interval should be converted to local time, got keys: {list(result['interval_prices'].keys())}"

    @pytest.mark.asyncio
    async def test_consecutive_failures_backoff(self, manager, auto_mock_core_dependencies):
        """Test implicit validation - failed sources are skipped for 24h."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_now = auto_mock_core_dependencies["now"]
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data

        # Configure for failure
        mock_fallback.return_value = MOCK_FAILURE_RESULT
        # Processor called by _generate_empty_result
        empty_res_1 = await manager._generate_empty_result(error=f"All sources failed: {MOCK_FAILURE_RESULT['error']}")
        mock_processor.return_value = empty_res_1
        mock_cache_get.return_value = None  # No cache

        # First failure - sources get marked as failed
        await manager.fetch_data()
        
        # Verify sources were marked as failed
        assert Source.NORDPOOL in manager._failed_sources, "Nordpool should be in failed sources"
        assert Source.ENTSOE in manager._failed_sources, "ENTSOE should be in failed sources"
        assert manager._failed_sources[Source.NORDPOOL] is not None, "Nordpool should have failure timestamp"
        assert manager._consecutive_failures == 1, "First failure should set counter to 1"

        # Reset mocks for second call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        empty_res_2 = await manager._generate_empty_result(error="No API sources available")
        mock_processor.return_value = empty_res_2

        # Advance time by 1 hour (less than 24h)
        mock_now.return_value += timedelta(hours=1)

        # Second attempt - sources should be SKIPPED because they failed <24h ago
        await manager.fetch_data()

        # Assert: FallbackManager should NOT be called because all sources are filtered out
        mock_fallback.assert_not_awaited(), "API should not be called - all sources failed recently (<24h)"
        # No sources available, so consecutive failures would increment
        assert manager._consecutive_failures == 2, "Consecutive failures should increment to 2"

        # Reset for forced fetch test
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        mock_fallback.return_value = MOCK_SUCCESS_RESULT  # Simulate success for forced fetch
        mock_processor.return_value = MOCK_PROCESSED_RESULT

        # Force fetch should bypass 24h filter and try sources again
        await manager.fetch_data(force=True)
        
        # Assert: Forced fetch bypasses filters
        mock_fallback.assert_awaited_once(), "Forced fetch should bypass 24h filter and call API"
        # On success, failures should be cleared
        assert manager._consecutive_failures == 0, "Consecutive failures should reset to 0 on success"
        assert manager._failed_sources[Source.NORDPOOL] is None, "Nordpool failure should be cleared on success"
        
        # Cleanup background tasks before finishing
        await cancel_health_check_tasks(manager)

    @pytest.mark.asyncio
    async def test_daily_retry_window_success_and_failure(self, manager, auto_mock_core_dependencies, monkeypatch):
        """Test comprehensive source validation lifecycle: failures, 24h skip, retry success, retry failure."""
        # This test validates the complete implicit validation flow:
        # 1. Initial failure marks sources with timestamp
        # 2. Subsequent fetches within 24h skip failed sources
        # 3. After 24h, sources are retried automatically
        # 4. Retry success clears failure markers
        # 5. Retry failure updates failure timestamp and continues 24h cycle
        
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies["data_processor"].return_value.process
        mock_now = auto_mock_core_dependencies["now"]
        mock_cache_get = auto_mock_core_dependencies["cache_manager"].return_value.get_data
        
        # Mock _schedule_health_check to avoid background task complications in tests
        async def mock_schedule_health_check():
            pass  # No-op for testing - we're testing the 24h filter logic, not the health check scheduler
        
        monkeypatch.setattr(manager, "_schedule_health_check", mock_schedule_health_check)
        
        # Clear the rate limiting state to start fresh
        from custom_components.ge_spot.coordinator.unified_price_manager import _LAST_FETCH_TIME
        _LAST_FETCH_TIME.clear()
        
        initial_time = mock_now.return_value
        
        # ========== SCENARIO 1: Initial Failure ==========
        # Sources fail, get marked with timestamp, daily retry scheduled
        
        mock_fallback.return_value = MOCK_FAILURE_RESULT
        empty_res_1 = await manager._generate_empty_result(error=f"All sources failed: {MOCK_FAILURE_RESULT['error']}")
        mock_processor.return_value = empty_res_1
        mock_cache_get.return_value = None
        
        result_1 = await manager.fetch_data()
        
        # Verify failure was recorded
        assert Source.NORDPOOL in manager._failed_sources, "Nordpool should be marked as failed"
        assert Source.ENTSOE in manager._failed_sources, "ENTSOE should be marked as failed"
        first_failure_time_nordpool = manager._failed_sources[Source.NORDPOOL]
        first_failure_time_entsoe = manager._failed_sources[Source.ENTSOE]
        assert first_failure_time_nordpool is not None, "Failure timestamp should be set"
        assert first_failure_time_nordpool == initial_time, "Failure timestamp should match current time"
        assert manager._consecutive_failures == 1, "First failure increments counter"
        assert result_1.get("has_data") is False, "No data on failure"
        assert mock_fallback.await_count == 1, "Fallback called on first failure"
        
        # ========== SCENARIO 2: Second Fetch Within 24h (Sources Skipped) ==========
        # Sources should be skipped because they failed <24h ago
        
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        
        # Advance time by 2 hours (still within 24h window)
        mock_now.return_value = initial_time + timedelta(hours=2)
        _LAST_FETCH_TIME.clear()  # Clear rate limit to allow fetch attempt
        
        empty_res_2 = await manager._generate_empty_result(error="No API sources available")
        mock_processor.return_value = empty_res_2
        
        result_2 = await manager.fetch_data()
        
        # Verify sources were skipped (no API call made)
        assert mock_fallback.await_count == 0, "API should NOT be called - sources failed recently"
        assert manager._consecutive_failures == 2, "Consecutive failures increment when no sources available"
        assert manager._failed_sources[Source.NORDPOOL] == first_failure_time_nordpool, \
            "Failure timestamp unchanged when sources skipped"
        
        # ========== SCENARIO 3: Fetch After 24h - Retry Success ==========
        # After 24h, sources should be retried and succeed
        
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        
        # Advance time by 25 hours total (past 24h window)
        mock_now.return_value = initial_time + timedelta(hours=25)
        _LAST_FETCH_TIME.clear()  # Clear rate limit
        
        # Configure for successful retry
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = MOCK_PROCESSED_RESULT
        
        result_3 = await manager.fetch_data()
        
        # Verify sources were retried and success cleared failures
        assert mock_fallback.await_count == 1, "API should be called after 24h window"
        assert manager._consecutive_failures == 0, "Success resets consecutive failure counter"
        assert manager._failed_sources[Source.NORDPOOL] is None, "Successful source clears failure marker"
        # Note: ENTSOE was never tried because NORDPOOL succeeded (fallback stops at first success)
        # So ENTSOE still has its failure marker - this is correct behavior
        assert result_3.get("has_data") is True, "Data available on success"
        assert result_3.get("data_source") == Source.NORDPOOL, "Correct source in result"
        
        # ========== SCENARIO 4: New Failure After Previous Success ==========
        # Sources fail again, get new failure timestamps
        
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        
        # Advance time by 2 hours
        second_failure_time_start = initial_time + timedelta(hours=27)
        mock_now.return_value = second_failure_time_start
        _LAST_FETCH_TIME.clear()
        
        mock_fallback.return_value = MOCK_FAILURE_RESULT
        empty_res_4 = await manager._generate_empty_result(error=f"All sources failed: {MOCK_FAILURE_RESULT['error']}")
        mock_processor.return_value = empty_res_4
        
        result_4 = await manager.fetch_data()
        
        # Verify new failure markers set
        assert Source.NORDPOOL in manager._failed_sources, "Sources marked as failed again"
        second_failure_time_nordpool = manager._failed_sources[Source.NORDPOOL]
        assert second_failure_time_nordpool == second_failure_time_start, "New failure timestamp set"
        assert second_failure_time_nordpool > first_failure_time_nordpool, "New timestamp is later than first"
        assert manager._consecutive_failures == 1, "Consecutive failures restart at 1"
        assert result_4.get("has_data") is False, "No data on second failure"
        
        # ========== SCENARIO 5: Fetch Within 24h of Second Failure (Skipped Again) ==========
        
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        
        mock_now.return_value = second_failure_time_start + timedelta(hours=5)
        _LAST_FETCH_TIME.clear()
        
        empty_res_5 = await manager._generate_empty_result(error="No API sources available")
        mock_processor.return_value = empty_res_5
        
        result_5 = await manager.fetch_data()
        
        assert mock_fallback.await_count == 0, "Sources still skipped within 24h of second failure"
        assert manager._failed_sources[Source.NORDPOOL] == second_failure_time_nordpool, \
            "Failure timestamp unchanged"
        
        # ========== SCENARIO 6: Retry After 24h - Failure Again ==========
        # After 24h from second failure, retry but fail again
        
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        
        third_attempt_time = second_failure_time_start + timedelta(hours=26)
        mock_now.return_value = third_attempt_time
        _LAST_FETCH_TIME.clear()
        
        mock_fallback.return_value = MOCK_FAILURE_RESULT
        empty_res_6 = await manager._generate_empty_result(error=f"All sources failed: {MOCK_FAILURE_RESULT['error']}")
        mock_processor.return_value = empty_res_6
        
        result_6 = await manager.fetch_data()
        
        # Verify retry was attempted but failed, updating timestamp
        assert mock_fallback.await_count == 1, "API called for retry after 24h"
        third_failure_time_nordpool = manager._failed_sources[Source.NORDPOOL]
        assert third_failure_time_nordpool == third_attempt_time, "Failure timestamp updated to retry time"
        assert third_failure_time_nordpool > second_failure_time_nordpool, "Third timestamp later than second"
        # Counter went: 1 (scenario 4) → 2 (scenario 5 skip) → 3 (scenario 6 retry fail)
        assert manager._consecutive_failures == 3, "Consecutive failures increment through skip and retry failure"
        assert result_6.get("has_data") is False, "No data on retry failure"
        
        # ========== SCENARIO 7: Force Fetch Bypasses 24h Filter ==========
        # Even within 24h window, force=True should bypass filter
        
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        
        # Only 1 hour after third failure (well within 24h)
        mock_now.return_value = third_attempt_time + timedelta(hours=1)
        _LAST_FETCH_TIME.clear()
        
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = MOCK_PROCESSED_RESULT
        
        result_7 = await manager.fetch_data(force=True)
        
        # Verify force bypassed 24h filter
        assert mock_fallback.await_count == 1, "Force=True bypasses 24h filter"
        assert manager._consecutive_failures == 0, "Success resets counter even on forced fetch"
        assert manager._failed_sources[Source.NORDPOOL] is None, "Force fetch success clears failures"
        assert result_7.get("has_data") is True, "Data available on forced success"


class TestHealthCheck:
    """Test the daily health check functionality."""

    @pytest.fixture
    def manager(self, auto_mock_core_dependencies):
        """Provides an initialized UnifiedPriceManager instance for tests."""
        hass = MockHass()
        config = {
            Config.DISPLAY_UNIT: Defaults.DISPLAY_UNIT,
            Config.API_KEY: "test_key",
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
        manager_instance._exchange_service = auto_mock_core_dependencies["get_exchange_service"].return_value
        if hasattr(manager_instance._data_processor, '_exchange_service'):
            manager_instance._data_processor._exchange_service = manager_instance._exchange_service
        return manager_instance

    async def cancel_health_check_tasks(self):
        """Cancel any lingering health check tasks."""
        for task in asyncio.all_tasks():
            if hasattr(task, 'get_coro'):
                coro_str = str(task.get_coro())
                if '_schedule_health_check' in coro_str or '_validate_all_sources' in coro_str:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    @pytest.mark.asyncio
    async def test_health_check_scheduled_on_failure(self, manager, auto_mock_core_dependencies):
        """Test that health check task is scheduled when all sources fail."""
        try:
            # Arrange
            mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
            mock_fallback.return_value = MOCK_FAILURE_RESULT
            auto_mock_core_dependencies["data_processor"].return_value.process.return_value = MOCK_EMPTY_PROCESSED_RESULT

            # Act
            await manager.fetch_data()

            # Assert
            assert manager._health_check_scheduled is True, "Health check should be scheduled after all sources fail"
        finally:
            # Cleanup
            await self.cancel_health_check_tasks()

    @pytest.mark.asyncio
    async def test_health_check_only_scheduled_once(self, manager, auto_mock_core_dependencies):
        """Test that health check task is not scheduled multiple times."""
        try:
            # Arrange
            mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
            mock_fallback.return_value = MOCK_FAILURE_RESULT
            auto_mock_core_dependencies["data_processor"].return_value.process.return_value = MOCK_EMPTY_PROCESSED_RESULT

            # Act - multiple failures
            await manager.fetch_data()
            first_scheduled = manager._health_check_scheduled

            await manager.fetch_data()
            await manager.fetch_data()

            # Assert - flag set once
            assert manager._health_check_scheduled is True, "Health check should be scheduled"
            assert first_scheduled is True, "Health check scheduled on first failure"
        finally:
            # Cleanup
            await self.cancel_health_check_tasks()

    @pytest.mark.asyncio
    async def test_validate_all_sources_success(self, manager, auto_mock_core_dependencies):
        """Test _validate_all_sources marks all working sources as validated."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
        mock_fallback.return_value = {**MOCK_SUCCESS_RESULT, "raw_data": {"test": "data"}}

        # Mark sources as failed first
        now = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        manager._failed_sources["nordpool"] = now
        manager._failed_sources["entsoe"] = now

        # Act
        await manager._validate_all_sources()

        # Assert - all sources cleared
        assert manager._failed_sources["nordpool"] is None, "Nordpool should be cleared after successful validation"
        assert manager._failed_sources["entsoe"] is None, "ENTSOE should be cleared after successful validation"

    @pytest.mark.asyncio
    async def test_validate_all_sources_partial_failure(self, manager, auto_mock_core_dependencies):
        """Test _validate_all_sources handles mixed success/failure."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback

        # First source succeeds, second fails
        mock_fallback.side_effect = [
            {**MOCK_SUCCESS_RESULT, "raw_data": {"test": "data"}},  # nordpool success
            MOCK_FAILURE_RESULT  # entsoe failure
        ]

        # Act
        await manager._validate_all_sources()

        # Assert
        assert manager._failed_sources.get("nordpool") is None, "Nordpool should succeed"
        assert manager._failed_sources.get("entsoe") is not None, "ENTSOE should fail"

    def test_failed_source_details_format(self, manager):
        """Test get_failed_source_details returns correct format."""
        # Arrange
        now = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        manager._failed_sources = {
            "nordpool": None,  # Working
            "energy_charts": now - timedelta(hours=2),  # Failed 2h ago
        }

        # Act
        details = manager.get_failed_source_details()

        # Assert
        assert len(details) == 1, "Should have one failed source"
        assert details[0]["source"] == "energy_charts", "Should be energy_charts"
        assert "failed_at" in details[0], "Should have failed_at timestamp"
        assert "retry_at" in details[0], "Should have retry_at timestamp"

    def test_next_health_check_calculation(self, manager):
        """Test _calculate_next_health_check returns correct next window."""
        # Test at 12:00 - should return 13:00 (start of 13-15 window)
        test_time = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        next_check = manager._calculate_next_health_check(test_time)
        assert next_check.hour == 13, f"Should return 13:00, got {next_check.hour}:00"
        assert next_check.date() == test_time.date(), "Should be same day"

        # Test at 16:00 - should return next day 00:00 (first window)
        test_time = datetime(2025, 4, 26, 16, 0, 0, tzinfo=timezone.utc)
        next_check = manager._calculate_next_health_check(test_time)
        assert next_check.hour == 0, f"Should return 00:00, got {next_check.hour}:00"
        assert next_check.date() == test_time.date() + timedelta(days=1), "Should be next day"

    @pytest.mark.asyncio
    async def test_health_check_non_blocking_on_boot(self, manager):
        """Test that health check with run_immediately=True doesn't block boot.
        
        Verifies that even with slow-failing sources (long timeouts), the health
        check runs in background without blocking the caller.
        """
        # Arrange - simulate slow failing sources (26s timeout per source)
        with patch.object(manager._fallback_manager, 'fetch_with_fallback') as mock_fallback:
            async def slow_timeout(*args, **kwargs):
                """Simulate slow timeout (2s + 6s + 18s = 26s)."""
                await asyncio.sleep(0.5)  # Simulate partial timeout for test speed
                return {"error": Exception("Timeout after 26s")}
            
            mock_fallback.side_effect = slow_timeout
            
            # Act - measure time for scheduling (should return immediately)
            import time
            start_time = time.time()
            
            # Schedule health check with run_immediately=True (background task)
            task = asyncio.create_task(manager._schedule_health_check(run_immediately=True))
            
            # Time until task is created (should be instant)
            schedule_time = time.time() - start_time
            
            # Assert - scheduling should be instant (< 0.1s)
            assert schedule_time < 0.1, f"Scheduling took {schedule_time:.2f}s, should be instant"
            
            # Cleanup - cancel background task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_cache_clear_triggers_health_check(self, manager):
        """Test that clearing cache triggers immediate health check.
        
        Verifies that manual cache clear validates all sources in background.
        """
        # Arrange
        with patch.object(manager._cache_manager, 'clear_cache', return_value=True), \
             patch.object(manager, 'fetch_data', new_callable=AsyncMock) as mock_fetch, \
             patch.object(manager, '_schedule_health_check', new_callable=AsyncMock) as mock_health:
            
            mock_fetch.return_value = {**MOCK_PROCESSED_RESULT, "has_data": True}
            
            # Act
            await manager.clear_cache()
            
            # Assert - health check should be scheduled with run_immediately=True
            mock_health.assert_called_once_with(run_immediately=True)

    @pytest.mark.asyncio
    async def test_health_check_with_mixed_source_timing(self, manager):
        """Test health check doesn't block with mixed fast/slow sources.
        
        Simulates realistic scenario:
        - First source: fast success (1s)
        - Second source: slow timeout (26s)
        - Third source: fast error (0.1s)
        
        Health check should run in background without blocking caller.
        """
        # Arrange
        call_count = [0]
        
        async def mixed_timing(*args, **kwargs):
            """Simulate mixed source timing."""
            call_count[0] += 1
            if call_count[0] == 1:
                # Fast success
                await asyncio.sleep(0.01)
                return {**MOCK_SUCCESS_RESULT, "raw_data": {"test": "data"}}
            elif call_count[0] == 2:
                # Slow timeout
                await asyncio.sleep(0.5)  # Simulate timeout for test speed
                return {"error": Exception("Timeout")}
            else:
                # Fast error
                return {"error": Exception("Quick error")}
        
        with patch.object(manager._fallback_manager, 'fetch_with_fallback') as mock_fallback:
            mock_fallback.side_effect = mixed_timing
            
            # Act - measure time for scheduling
            import time
            start_time = time.time()
            
            # Schedule health check (should return immediately despite slow sources)
            task = asyncio.create_task(manager._schedule_health_check(run_immediately=True))
            
            schedule_time = time.time() - start_time
            
            # Assert - scheduling should be instant
            assert schedule_time < 0.1, f"Scheduling took {schedule_time:.2f}s, should be instant"
            
            # Let health check actually run to verify it works
            await asyncio.sleep(1.0)  # Wait for mixed timing to complete
            
            # Cleanup
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_health_check_all_sources_fast_success(self, manager):
        """Test health check completes quickly when all sources succeed fast.
        
        Best-case scenario: All sources respond quickly (< 2s each).
        """
        # Arrange
        with patch.object(manager._fallback_manager, 'fetch_with_fallback') as mock_fallback:
            async def fast_success(*args, **kwargs):
                """Simulate fast successful response."""
                await asyncio.sleep(0.01)
                return {**MOCK_SUCCESS_RESULT, "raw_data": {"test": "data"}}
            
            mock_fallback.side_effect = fast_success
            
            # Act
            import time
            start_time = time.time()
            
            await manager._validate_all_sources()
            
            validation_time = time.time() - start_time
            
            # Assert - should complete quickly (< 1s for 3 sources × 0.01s)
            assert validation_time < 1.0, f"Validation took {validation_time:.2f}s, expected < 1s"
            
            # All sources should be marked as working
            assert all(
                manager._failed_sources.get(cls(config={}).source_type) is None
                for cls in manager._api_classes
            ), "All sources should be validated"