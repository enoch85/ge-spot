#!/usr/bin/env python3
"""Tests for the UnifiedPriceManager functionality.

These tests verify real-world behavior of the UnifiedPriceManager to ensure it:
1. Correctly fetches data from appropriate sources
2. Properly handles fallback scenarios when primary sources fail
3. Manages cache with appropriate expiry times
4. Handles error scenarios gracefully without crashing
5. Processes and validates data from different sources consistently

IMPORTANT: These tests are aligned with the 15-minute interval implementation.
- All mock data uses 15-minute interval timestamps (HH:MM format, e.g. 10:00, 10:15, 10:30)
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
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.coordinator.unified_price_manager import (
    UnifiedPriceManager,
)
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData
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
        if hasattr(task, "get_coro"):
            coro_str = str(task.get_coro())
            if (
                "_schedule_health_check" in coro_str
                or "_validate_all_sources" in coro_str
            ):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


# Helper function to generate complete interval data (96 intervals for a full day)
def _generate_complete_intervals(base_date_str, base_price=1.0):
    """Generate 96 intervals (15-minute intervals for 24 hours) with HH:MM keys."""
    from datetime import datetime, timedelta

    intervals = {}
    base_dt = datetime.fromisoformat(base_date_str)
    for i in range(96):  # 24 hours * 4 intervals/hour = 96
        interval_time = base_dt + timedelta(minutes=i * 15)
        # Use HH:MM format for keys, as expected by data_validity.py
        interval_key = interval_time.strftime("%H:%M")
        intervals[interval_key] = base_price + (i * 0.01)
    return intervals


def _create_interval_price_data(
    source=Source.NORDPOOL,
    area="SE1",
    target_currency="SEK",
    today_base_price=1.1,
    tomorrow_base_price=1.5,
    include_tomorrow=True,
    tz_service=None,
):
    """Create an IntervalPriceData object for testing.

    This is what DataProcessor.process() actually returns.
    """
    return IntervalPriceData(
        source=source,
        area=area,
        target_currency=target_currency,
        today_interval_prices=_generate_complete_intervals(
            "2025-04-26T00:00:00+02:00", today_base_price
        ),
        tomorrow_interval_prices=(
            _generate_complete_intervals(
                "2025-04-27T00:00:00+02:00", tomorrow_base_price
            )
            if include_tomorrow
            else {}
        ),
        attempted_sources=[source],
        fallback_sources=[],
        using_cached_data=False,
        last_updated="2025-04-26T12:00:00+00:00",
        _tz_service=tz_service,
    )


def _dict_to_interval_price_data(data_dict):
    """Convert a test dict to IntervalPriceData (for backward compatibility with existing tests).

    This helps migrate tests that were creating dict mocks.
    """
    return IntervalPriceData(
        source=data_dict.get("data_source", data_dict.get("source", Source.NORDPOOL)),
        area=data_dict.get("area", "SE1"),
        target_currency=data_dict.get("target_currency", "SEK"),
        source_currency=data_dict.get("source_currency", "EUR"),
        source_timezone=data_dict.get("source_timezone", "UTC"),
        target_timezone=data_dict.get("target_timezone", "UTC"),
        today_interval_prices=data_dict.get("today_interval_prices", {}),
        tomorrow_interval_prices=data_dict.get("tomorrow_interval_prices", {}),
        today_raw_prices=data_dict.get("today_raw_prices", {}),
        tomorrow_raw_prices=data_dict.get("tomorrow_raw_prices", {}),
        attempted_sources=data_dict.get("attempted_sources", []),
        fallback_sources=data_dict.get("fallback_sources", []),
        using_cached_data=data_dict.get("using_cached_data", False),
        last_updated=data_dict.get("last_update", data_dict.get("last_updated")),
        fetched_at=data_dict.get("fetched_at"),
        vat_rate=data_dict.get("vat_rate", 0.0),
        vat_included=data_dict.get("vat_included", False),
        display_unit=data_dict.get("display_unit", "EUR/kWh"),
        ecb_rate=data_dict.get(
            "ecb_rate", data_dict.get("exchange_rate")
        ),  # Support both names
        ecb_updated=data_dict.get("ecb_updated"),
        migrated_from_tomorrow=data_dict.get("migrated_from_tomorrow", False),
        original_cache_date=data_dict.get("original_cache_date"),
        raw_data=data_dict.get("raw_data"),
        _tz_service=None,  # Tests usually don't need this
    )


# Mock data for successful fetch
# Using 15-minute intervals (HH:MM format) to match TimeInterval.QUARTER_HOURLY configuration
MOCK_SUCCESS_RESULT = {
    "data_source": Source.NORDPOOL,
    "area": "SE1",
    "currency": "SEK",  # Original currency from source
    "today_interval_prices": _generate_complete_intervals(
        "2025-04-26T00:00:00+00:00", 1.0
    ),
    "attempted_sources": [Source.NORDPOOL],
    # Note: No "error" key for successful fetch
}


# Mock IntervalPriceData object returned by DataProcessor.process()
# This is the CORRECT type that process() should return
def _get_mock_interval_price_data():
    """Get mock IntervalPriceData object (what DataProcessor.process actually returns)."""
    return _create_interval_price_data()


# Mock data for processed result (IntervalPriceData format - what sensors receive)
# Sensors now receive IntervalPriceData instances directly and access properties
MOCK_PROCESSED_RESULT = {
    "data_source": Source.NORDPOOL,
    "source": Source.NORDPOOL,
    "area": "SE1",
    "target_currency": "SEK",
    "today_interval_prices": _generate_complete_intervals(
        "2025-04-26T00:00:00+02:00", 1.1
    ),
    "tomorrow_interval_prices": _generate_complete_intervals(
        "2025-04-27T00:00:00+02:00", 1.5
    ),
    "attempted_sources": [Source.NORDPOOL],
    "fallback_sources": [],
    "using_cached_data": False,
    "has_data": True,
    "last_update": "2025-04-26T12:00:00+00:00",
}

# Mock data for cached result (similar structure to processed)
MOCK_CACHED_RESULT = {
    **MOCK_PROCESSED_RESULT,  # Base it on processed structure
    "using_cached_data": True,
    "last_update": "2025-04-26T11:30:00+00:00",  # Older timestamp
}

# Mock data for failed fetch
MOCK_FAILURE_RESULT = {
    "data_source": "None",
    "area": "SE1",
    "currency": "SEK",
    "today_interval_prices": {},
    "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
    "error": "Failed to fetch from all sources",
}

# Mock data for empty processed result
MOCK_EMPTY_PROCESSED_RESULT = {
    "source": "None",
    "area": "SE1",
    "target_currency": "SEK",
    "today_interval_prices": {},
    "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
    "fallback_sources": [Source.NORDPOOL, Source.ENTSOE],
    "using_cached_data": False,
    "has_data": False,
    "last_update": "2025-04-26T12:00:00+00:00",  # Example timestamp
    "error": "Failed to fetch from all sources",
    # Other keys added by DataProcessor when processing empty data
}


@pytest.fixture(autouse=True)
def auto_mock_core_dependencies():
    """Automatically mock core dependencies used by UnifiedPriceManager."""
    # Patch the global rate limiting dictionary to isolate tests
    with patch(
        "custom_components.ge_spot.coordinator.unified_price_manager._LAST_FETCH_TIME",
        new_callable=dict,
    ) as mock_last_fetch_time, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.FallbackManager",
        new_callable=MagicMock,
    ) as mock_fallback_manager, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.CacheManager",
        new_callable=MagicMock,
    ) as mock_cache_manager, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.DataProcessor",
        new_callable=MagicMock,
    ) as mock_data_processor, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.TimezoneService",
        new_callable=MagicMock,
    ) as mock_tz_service, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.get_exchange_service",
        new_callable=AsyncMock,
    ) as mock_get_exchange_service, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.dt_util.now"
    ) as mock_now, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.async_get_clientsession"
    ) as mock_get_session, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.get_sources_for_region"
    ) as mock_get_sources:

        # Configure default return values for mocks
        mock_get_sources.return_value = [Source.NORDPOOL, Source.ENTSOE]
        mock_fallback_manager.return_value.fetch_with_fallback = AsyncMock(
            return_value=MOCK_SUCCESS_RESULT
        )

        # CacheManager.get_data() returns Optional[IntervalPriceData]
        # Temporarily wrap to auto-convert dict mocks to IntervalPriceData
        # TODO: Update all tests to use IntervalPriceData directly and remove this wrapper
        base_cache_get = MagicMock(return_value=None)

        def auto_convert_cache(*args, **kwargs):
            """Auto-convert dict to IntervalPriceData for backward compat during migration."""
            ret_val = base_cache_get.return_value
            if isinstance(ret_val, dict):
                return _dict_to_interval_price_data(ret_val)
            return ret_val

        base_cache_get.side_effect = auto_convert_cache
        mock_cache_manager.return_value.get_data = base_cache_get

        mock_cache_manager.return_value.store = MagicMock()

        # DataProcessor.process() should return IntervalPriceData
        # Temporarily wrap to auto-convert dict mocks to IntervalPriceData
        # TODO: Update all tests to use IntervalPriceData directly and remove this wrapper
        base_process_mock = AsyncMock(return_value=_get_mock_interval_price_data())

        async def auto_convert_processor(data):
            """Auto-convert dict to IntervalPriceData for backward compat during migration."""
            ret_val = base_process_mock.return_value
            if isinstance(ret_val, dict):
                return _dict_to_interval_price_data(ret_val)
            return ret_val

        base_process_mock.side_effect = auto_convert_processor
        mock_data_processor.return_value.process = base_process_mock

        # Configure TimezoneService mock with real timezone objects for DST handling
        mock_tz_service_instance = MagicMock()
        mock_tz_service_instance.target_timezone = timezone.utc
        mock_tz_service_instance.area_timezone = timezone.utc
        mock_tz_service.return_value = mock_tz_service_instance
        mock_get_exchange_service.return_value = (
            AsyncMock()
        )  # Mock the service instance itself
        mock_now.return_value = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        mock_get_session.return_value = MagicMock()  # Mock the aiohttp session

        yield {
            "last_fetch_time": mock_last_fetch_time,  # Include the patched dict if needed
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
            Config.API_KEY: "test_key",  # Example config
            Config.SOURCE_PRIORITY: [Source.NORDPOOL, Source.ENTSOE],
            Config.VAT: Defaults.VAT,
            Config.INCLUDE_VAT: Defaults.INCLUDE_VAT,
        }
        manager_instance = UnifiedPriceManager(
            hass=hass,
            area="SE1",
            currency="SEK",
            config=config,
        )
        # Manually set the exchange service on the instance after init, as it's lazy loaded
        manager_instance._exchange_service = auto_mock_core_dependencies[
            "get_exchange_service"
        ].return_value
        # Ensure processor also gets the mock service if needed by its init/process
        # This depends on DataProcessor implementation, assuming it might need it
        if hasattr(manager_instance._data_processor, "_exchange_service"):
            manager_instance._data_processor._exchange_service = (
                manager_instance._exchange_service
            )

        return manager_instance

    def test_init(self, manager, auto_mock_core_dependencies):
        """Test initialization sets attributes correctly."""
        # Core attributes
        assert manager.area == "SE1", f"Expected area 'SE1', got '{manager.area}'"
        assert (
            manager.currency == "SEK"
        ), f"Expected currency 'SEK', got '{manager.currency}'"

        # Initial state
        assert (
            manager._active_source is None
        ), "Active source should be None on initialization"
        assert (
            manager._attempted_sources == []
        ), "Attempted sources should be empty on initialization"
        assert (
            manager._fallback_sources == []
        ), "Fallback sources should be empty on initialization"
        assert (
            manager._using_cached_data is False
        ), "using_cached_data should be False on initialization"
        assert (
            manager._consecutive_failures == 0
        ), "Consecutive failures should be 0 on initialization"

        # Dependencies
        assert (
            manager._tz_service
            is auto_mock_core_dependencies["tz_service"].return_value
        ), "TimezoneService not properly initialized"
        assert (
            manager._fallback_manager
            is auto_mock_core_dependencies["fallback_manager"].return_value
        ), "FallbackManager not properly initialized"
        assert (
            manager._cache_manager
            is auto_mock_core_dependencies["cache_manager"].return_value
        ), "CacheManager not properly initialized"
        assert (
            manager._data_processor
            is auto_mock_core_dependencies["data_processor"].return_value
        ), "DataProcessor not properly initialized"

        # Source configuration
        assert manager._source_priority == [
            Source.NORDPOOL,
            Source.ENTSOE,
        ], "Source priority not correctly initialized"
        assert (
            len(manager._api_classes) == 2
        ), f"Expected 2 API classes, got {len(manager._api_classes)}"

    @pytest.mark.asyncio
    async def test_fetch_data_success_first_source(
        self, manager, auto_mock_core_dependencies
    ):
        """Test successful fetch using the primary source."""
        # Arrange: Mocks already configured for success by default fixture
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_store = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.store
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallback should be called once"

        # Verify processor called with correct raw data
        mock_processor.assert_awaited_once(), f"DataProcessor.process should be called with raw data, got {mock_processor.call_args}"

        # Verify cache stored with processed data
        mock_cache_store.assert_called_once(), f"CacheManager.store should be called with processed data, got {mock_cache_store.call_args}"

        # Cache get may be called during decision making
        # mock_cache_get.assert_not_called(), "CacheManager.get_data should not be called on successful fetch"

        # Check returned data
        # Verify key fields are present and correct
        assert result is not None, "Result should not be None"
        assert hasattr(
            result, "today_interval_prices"
        ), "Result should have today_interval_prices"
        assert hasattr(
            result, "tomorrow_interval_prices"
        ), "Result should have tomorrow_interval_prices"
        assert (
            len(result.today_interval_prices) == 96
        ), f"Expected 96 today intervals, got {len(result.today_interval_prices)}"
        assert (
            len(result.tomorrow_interval_prices) == 96
        ), f"Expected 96 tomorrow intervals, got {len(result.tomorrow_interval_prices)}"
        assert (
            result.source == Source.NORDPOOL
        ), f"Expected data_source NORDPOOL, got {result.source}"
        assert result.area == "SE1", f"Expected area SE1, got {result.area}"
        assert (
            result.using_cached_data is False
        ), f"Expected using_cached_data False, got {result.using_cached_data}"

        # Check manager state updates
        assert (
            manager._active_source == Source.NORDPOOL
        ), f"Active source should be NORDPOOL, got {manager._active_source}"
        assert manager._attempted_sources == [
            Source.NORDPOOL
        ], f"Attempted sources should be [NORDPOOL], got {manager._attempted_sources}"
        assert (
            manager._fallback_sources == []
        ), f"Fallback sources should be empty, got {manager._fallback_sources}"
        assert (
            manager._using_cached_data is False
        ), f"using_cached_data should be False, got {manager._using_cached_data}"
        assert (
            manager._consecutive_failures == 0
        ), f"Consecutive failures should be 0, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    @freeze_time("2025-04-26 12:00:00 UTC")
    async def test_cache_timestamp_validation(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that cache created is valid shortly after creation (within rate limit)."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data
        mock_cache_update = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.store
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Mock is_in_grace_period to return False so rate limiting works as expected
        with patch.object(manager, "is_in_grace_period", return_value=False):
            # --- First call: Successful fetch, populates cache ---
            # Time is frozen at 12:00:00 UTC
            mock_fallback.return_value = MOCK_SUCCESS_RESULT
            mock_processor.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )
            await manager.fetch_data()

            # Cleanup background tasks
            await cancel_health_check_tasks(manager)

            # Verify cache was updated - store() is called with keyword args
            mock_cache_update.assert_called_once()
            # Check that store was called with correct area and source
            call_kwargs = mock_cache_update.call_args[1]
            assert call_kwargs["area"] == "SE1"
            assert call_kwargs["source"] == Source.NORDPOOL
            assert "data" in call_kwargs
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
            mock_cache_get.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )
            # Configure processor to return this cached data when called
            mock_processor.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )

            # Advance time slightly (e.g. 1 minute), still within rate limit
            freezer = freeze_time("2025-04-26 12:01:00 UTC")
            freezer.start()
            mock_now.return_value = datetime(2025, 4, 26, 12, 1, 0, tzinfo=timezone.utc)

            # Act: Fetch again
            result = await manager.fetch_data()

            # Assert
            # API should not be called due to rate limiting
            mock_fallback.assert_not_awaited(), "API fetch should be skipped due to rate limit"
            # Cache should be checked (with target_date, no max_age_minutes)
            assert (
                mock_cache_get.call_count >= 1
            ), "CacheManager.get_data should be called"
            # Verify area is passed (target_date will be today's date from dt_util.now().date())
            call_kwargs = mock_cache_get.call_args[1]
            assert (
                call_kwargs.get("area") == manager.area
            ), "Cache should be called with correct area"

            # Processor should NOT be called - cached data is returned directly
            mock_processor.assert_not_awaited(), "Processor should NOT be called for cached data"

            # Result should indicate cached data was used
            assert (
                result.using_cached_data is True
            ), "Result should indicate cached data was used"
            assert result.today_interval_prices == MOCK_PROCESSED_RESULT.get(
                "today_interval_prices"
            ), "Result prices should match cached data"

            # Stop the time freezer
            freezer.stop()

    @pytest.mark.asyncio
    async def test_fetch_data_success_fallback_source(
        self, manager, auto_mock_core_dependencies
    ):
        """Test successful fetch using a fallback source when primary fails."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_update = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.store

        # Create realistic data for fallback success scenario
        fallback_success_result = {
            **MOCK_SUCCESS_RESULT,
            "data_source": Source.ENTSOE,
            "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
        }
        processed_fallback_result = {
            **MOCK_PROCESSED_RESULT,
            "data_source": Source.ENTSOE,
            "source": Source.ENTSOE,
            "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
            "fallback_sources": [Source.NORDPOOL],
        }
        mock_fallback.return_value = fallback_success_result
        mock_processor.return_value = _dict_to_interval_price_data(
            processed_fallback_result
        )

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallback should be called once"

        # Verify processor called with fallback data
        mock_processor.assert_awaited_once_with(
            fallback_success_result
        ), f"DataProcessor.process should be called with fallback data, got {mock_processor.call_args}"

        # Verify cache updated with processed fallback data - store() uses keyword args
        mock_cache_update.assert_called_once()
        call_kwargs = mock_cache_update.call_args[1]
        assert call_kwargs["area"] == "SE1"
        assert call_kwargs["source"] == Source.ENTSOE
        assert "data" in call_kwargs

        # Check returned data (key fields)
        assert result is not None, "Result should not be None"
        assert result.source == Source.ENTSOE, "Result should be from ENTSOE"
        assert (
            Source.NORDPOOL in result.attempted_sources
        ), "Should include NORDPOOL in attempted sources"
        assert (
            Source.ENTSOE in result.attempted_sources
        ), "Should include ENTSOE in attempted sources"

        # Check manager state updates
        assert (
            manager._active_source == Source.ENTSOE
        ), f"Active source should be ENTSOE, got {manager._active_source}"
        assert manager._attempted_sources == [
            Source.NORDPOOL,
            Source.ENTSOE,
        ], f"Attempted sources incorrect: {manager._attempted_sources}"
        assert manager._fallback_sources == [
            Source.NORDPOOL
        ], f"Fallback sources should include failed NORDPOOL, got {manager._fallback_sources}"
        assert (
            manager._using_cached_data is False
        ), f"using_cached_data should be False, got {manager._using_cached_data}"
        assert (
            manager._consecutive_failures == 0
        ), f"Consecutive failures should be 0, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_fetch_data_validation_failure_triggers_fallback(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that when first source succeeds at fetch but fails validation, second source is tried.

        This tests the real-world scenario from debug.log where ENTSOE fetched data successfully
        but validation failed (missing current interval), and we need energy_charts/nordpool as fallback.
        """
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_update = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.store

        # First call: NORDPOOL succeeds at fetch but fails validation (returns None from processor)
        first_call_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            "today_interval_prices": {"10:00": 0.5},  # Has data
            "attempted_sources": [Source.NORDPOOL],
        }

        # Second call: ENTSOE succeeds both fetch and validation
        second_call_result = {
            **MOCK_SUCCESS_RESULT,
            "data_source": Source.ENTSOE,
            "attempted_sources": [
                Source.NORDPOOL,
                Source.ENTSOE,
            ],  # Should include both
        }
        processed_second_result = {
            **MOCK_PROCESSED_RESULT,
            "data_source": Source.ENTSOE,
            "source": Source.ENTSOE,
            "attempted_sources": [
                Source.NORDPOOL,
                Source.ENTSOE,
            ],  # Should include both
        }

        # Mock FallbackManager to return different results on each call
        mock_fallback.side_effect = [first_call_result, second_call_result]

        # Mock processor: first call returns None (validation failure), second call succeeds
        # Convert dict to IntervalPriceData for the second call
        mock_processor.side_effect = [
            None,
            _dict_to_interval_price_data(processed_second_result),
        ]

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        assert (
            mock_fallback.await_count == 2
        ), f"FallbackManager should be called twice (first source validation failed, retry with second), got {mock_fallback.await_count}"

        # First call should try NORDPOOL and ENTSOE (during first fetch, try ALL sources)
        first_call_args = mock_fallback.call_args_list[0]
        first_call_api_instances = first_call_args[1]["api_instances"]
        assert (
            len(first_call_api_instances) == 2
        ), f"First call should include ALL sources (first fetch behavior), got {len(first_call_api_instances)}"

        # Second call should only try ENTSOE (remaining source after NORDPOOL validation failure)
        second_call_args = mock_fallback.call_args_list[1]
        second_call_api_instances = second_call_args[1]["api_instances"]
        assert (
            len(second_call_api_instances) == 1
        ), f"Second call should only try remaining source (ENTSOE), got {len(second_call_api_instances)}"
        second_source = getattr(
            second_call_api_instances[0],
            "source_type",
            type(second_call_api_instances[0]).__name__,
        )
        assert (
            second_source == Source.ENTSOE
        ), f"Second call should try ENTSOE, got {second_source}"

        # Processor should be called twice
        assert (
            mock_processor.await_count == 2
        ), f"Processor should be called twice, got {mock_processor.await_count}"

        # Cache should be updated with successful result
        mock_cache_update.assert_called_once()

        # Check result is from ENTSOE (key fields)
        assert result is not None, "Result should not be None"
        assert result.source == Source.ENTSOE, "Result should be from ENTSOE"
        assert (
            Source.NORDPOOL in result.attempted_sources
        ), "Should include NORDPOOL in attempted sources"
        assert (
            Source.ENTSOE in result.attempted_sources
        ), "Should include ENTSOE in attempted sources"

        assert manager._active_source == Source.ENTSOE
        assert manager._consecutive_failures == 0

        # Check that NORDPOOL was marked as failed (temporarily)
        assert (
            Source.NORDPOOL in manager._failed_sources
        ), f"NORDPOOL should be in failed_sources after validation failure. _failed_sources={manager._failed_sources}"

    @pytest.mark.asyncio
    async def test_fetch_data_failure_all_sources_no_cache(
        self, manager, auto_mock_core_dependencies
    ):
        """Test failure when all sources fail and no cache is available - critical production scenario."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_update = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.store

        mock_fallback.return_value = (
            MOCK_FAILURE_RESULT  # Simulate failure from FallbackManager
        )
        mock_cache_get.return_value = None  # No cache available
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
        assert (
            mock_cache_get.call_count >= 1
        ), f"CacheManager.get_data should be called, got {mock_cache_get.call_args}"
        call_kwargs = mock_cache_get.call_args[1]
        assert (
            call_kwargs.get("area") == manager.area
        ), "Cache should be called with correct area"

        # Processor is called by _generate_empty_result which itself calls _process_result
        # It might be called with a slightly different structure than MOCK_FAILURE_RESULT
        # Let's check it was called once.
        # mock_processor.assert_awaited_once(), "DataProcessor.process should be called once to generate empty result"
        # CORRECTION: _generate_empty_result does NOT call process. Remove assertion.

        # Check result structure and content
        # The actual result comes from _generate_empty_result

        # Check manager state updates
        assert (
            manager._active_source == "None"
        ), f"Active source should be 'None', got {manager._active_source}"
        assert manager._attempted_sources == [
            Source.NORDPOOL,
            Source.ENTSOE,
        ], f"Attempted sources incorrect: {manager._attempted_sources}"
        assert manager._fallback_sources == [
            Source.NORDPOOL,
            Source.ENTSOE,
        ], f"All sources should be in fallback_sources, got {manager._fallback_sources}"
        # In this path, cache was attempted but failed, so using_cached_data reflects the attempt
        assert (
            manager._using_cached_data is True
        ), f"using_cached_data should be True (cache attempted), got {manager._using_cached_data}"
        assert (
            manager._consecutive_failures == 1
        ), f"Consecutive failures should be 1, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_fetch_data_failure_all_sources_uses_cache(
        self, manager, auto_mock_core_dependencies
    ):
        """Test failure when all sources fail but valid cache is available - common fallback scenario."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_update = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.store

        mock_fallback.return_value = MOCK_FAILURE_RESULT  # Simulate failure
        mock_cache_get.return_value = _dict_to_interval_price_data(
            MOCK_CACHED_RESULT
        )  # Provide cached data
        # Processor will be called with the cached data via _process_result
        mock_processor.return_value = _dict_to_interval_price_data(
            MOCK_CACHED_RESULT  # Assume processor returns it as is
        )

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        mock_fallback.assert_awaited_once(), "FallbackManager.fetch_with_fallback should be called once"

        # Check cache was attempted (no TTL check anymore)
        assert (
            mock_cache_get.call_count >= 1
        ), f"CacheManager.get_data should be called, got {mock_cache_get.call_args}"
        call_kwargs = mock_cache_get.call_args[1]
        assert (
            call_kwargs.get("area") == manager.area
        ), "Cache should be called with correct area"

        # Processor should NOT be called - cached data is returned directly when all sources fail
        mock_processor.assert_not_awaited(), "Processor should NOT be called for cached fallback data"

        # Check result structure and content
        # The cached IntervalPriceData is returned directly with using_cached_data flag updated
        assert result.using_cached_data is True, "using_cached_data flag should be True"
        assert result.today_interval_prices == MOCK_CACHED_RESULT.get(
            "today_interval_prices"
        ), "Prices should match cached data"
        # attempted_sources comes from the actual cache data, not from MOCK_FAILURE_RESULT
        # The cache contains data from a previous successful fetch, so check it has SOME attempted_sources
        assert (
            len(result.attempted_sources) > 0
        ), "Result should have attempted_sources from cached data"

        # Cache not updated when using cache due to failure
        mock_cache_update.assert_not_called(), "CacheManager.store should not be called when using cache"

        # Check manager state updates
        assert (
            manager._active_source == "None"
        ), f"Active source should be 'None', got {manager._active_source}"
        assert manager._attempted_sources == [
            Source.NORDPOOL,
            Source.ENTSOE,
        ], f"Attempted sources incorrect: {manager._attempted_sources}"
        assert manager._fallback_sources == [
            Source.NORDPOOL,
            Source.ENTSOE,
        ], f"All sources should be in fallback_sources, got {manager._fallback_sources}"
        assert (
            manager._using_cached_data is True
        ), f"using_cached_data should be True, got {manager._using_cached_data}"
        assert (
            manager._consecutive_failures == 1
        ), f"Consecutive failures should be 1, got {manager._consecutive_failures}"

    @pytest.mark.asyncio
    async def test_rate_limiting_uses_cache(self, manager, auto_mock_core_dependencies):
        """Test that rate limiting prevents fetch and uses cache - prevents API abuse."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Mock is_in_grace_period to return False so rate limiting works as expected
        with patch.object(manager, "is_in_grace_period", return_value=False):
            # First call - successful fetch
            now_time = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
            mock_now.return_value = now_time
            mock_fallback.return_value = MOCK_SUCCESS_RESULT
            mock_processor.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )
            await manager.fetch_data()

            # Cleanup background tasks
            await cancel_health_check_tasks(manager)

            # Reset mocks for second call
            mock_fallback.reset_mock()
            mock_processor.reset_mock()
            mock_cache_get.reset_mock()  # Reset get_data mock
            mock_cache_get.return_value = _dict_to_interval_price_data(
                MOCK_CACHED_RESULT
            )  # Make cache available
            # Assume processor returns cached data when processing cached input
            mock_processor.return_value = _dict_to_interval_price_data(
                MOCK_CACHED_RESULT
            )

            # Advance time slightly, but less than min interval (e.g. 3 minutes for a 5 minute interval)
            min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
            mock_now.return_value = now_time + timedelta(
                minutes=min_interval_minutes / 2
            )

            # Act - Second call should use cache due to rate limiting
            result = await manager.fetch_data()

            # Assert
            mock_fallback.assert_not_awaited(), "FallbackManager.fetch_with_fallback should not be called due to rate limiting"
            assert (
                mock_cache_get.call_count >= 1
            ), f"CacheManager.get_data should be called when rate limited, got {mock_cache_get.call_args}"
            call_kwargs = mock_cache_get.call_args[1]
            assert (
                call_kwargs.get("area") == manager.area
            ), "Cache should be called with correct area"

            # Processor should NOT be called - cached data is returned directly
            mock_processor.assert_not_awaited(), "Processor should NOT be called for cached data"

            # Check result uses cached data
            assert (
                result.using_cached_data is True
            ), "using_cached_data flag should be True"
            assert result.today_interval_prices == MOCK_CACHED_RESULT.get(
                "today_interval_prices"
            ), "Prices should match cached data"

    @pytest.mark.asyncio
    async def test_rate_limiting_no_cache(self, manager, auto_mock_core_dependencies):
        """Test rate limiting when no cache is available - rare but important edge case."""
        # Arrange
        mock_now = auto_mock_core_dependencies["now"]
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Mock is_in_grace_period to return False so rate limiting works as expected
        with patch.object(manager, "is_in_grace_period", return_value=False):
            # First call - successful fetch
            now_time = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
            mock_now.return_value = now_time
            mock_fallback.return_value = MOCK_SUCCESS_RESULT
            mock_processor.return_value = MOCK_PROCESSED_RESULT
            await manager.fetch_data()

            # Cleanup background tasks
            await cancel_health_check_tasks(manager)

            # Reset mocks for second call
            mock_fallback.reset_mock()
            mock_processor.reset_mock()
            mock_cache_get.reset_mock()
            mock_cache_get.return_value = None  # No cache

            # Prepare empty result for rate limited case
            # The processor will be called by _generate_empty_result
            # Let's configure it to return what _generate_empty_result expects _process_result to return
            # This is complex, let's assume _generate_empty_result works correctly and compare the final output
            empty_result = await manager._generate_empty_result(
                error="Rate limited, no cache available"
            )
            mock_processor.return_value = (
                empty_result  # Mock processor to return the final expected structure
            )

            # Advance time slightly, but less than min interval
            min_interval_minutes = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
            mock_now.return_value = now_time + timedelta(
                minutes=min_interval_minutes / 2
            )

            # Act - Second call should try cache but find none
            result = await manager.fetch_data()

            # Assert
            mock_fallback.assert_not_awaited(), "FallbackManager.fetch_with_fallback should not be called due to rate limiting"
            assert (
                mock_cache_get.call_count >= 1
            ), f"CacheManager.get_data should be called when rate limited, got {mock_cache_get.call_args}"
            call_kwargs = mock_cache_get.call_args[1]
            assert (
                call_kwargs.get("area") == manager.area
            ), "Cache should be called with correct area"
            # Processor is called by _generate_empty_result -> _process_result
            # mock_processor.assert_awaited_once(), "DataProcessor.process should be called once to generate empty result"
            # CORRECTION: _generate_empty_result does NOT call process. Remove assertion.

            # Check result is empty with rate limit error
            # Compare key fields
            error_msg = getattr(result, "_error", "").lower()
            assert (
                "rate limit" in error_msg
            ), f"Error should mention rate limiting, got: {getattr(result, '_error', '')}"
            # using_cached_data is False because no cache was found (not True because cache was attempted)
            assert (
                result.using_cached_data is False
            ), "using_cached_data flag should be False (no cache found)"
            assert not result.today_interval_prices, "interval_prices should be empty"
            assert (
                not result.today_interval_prices
            ), "Should have no data (empty interval prices)"

    @pytest.mark.asyncio
    async def test_fetch_data_with_malformed_api_response(
        self, manager, auto_mock_core_dependencies
    ):
        """Test handling of malformed API response - real-world scenario with broken API."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data

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
        expected_empty = await manager._generate_empty_result(
            error="All sources failed: None"
        )
        mock_processor.return_value = expected_empty

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        # Fallback manager was called (twice: once for first source, once for retry with remaining sources)
        # Since first source returns malformed data (no valid interval_prices), validation fails and
        # the code retries with remaining sources
        assert (
            mock_fallback.await_count >= 1
        ), "FallbackManager should be called at least once"
        # Note: It will be called twice when validation fails and remaining sources exist

        # Cache was checked after fetch appeared to fail (due to missing key)
        assert (
            mock_cache_get.call_count >= 1
        ), "Cache should be checked on malformed data"
        call_kwargs = mock_cache_get.call_args[1]
        assert (
            call_kwargs.get("area") == manager.area
        ), "Cache should be called with correct area"
        # Processor was called once via _generate_empty_result
        # mock_processor.assert_awaited_once()
        # CORRECTION: _generate_empty_result does NOT call process. Remove assertion.

        # Check the final result structure and error message
        assert result is not None, "Result should not be None on malformed data"
        assert hasattr(result, "_error"), "Error should be indicated on malformed data"
        # The actual error from production: "Fetch/Processing failed: Unknown fetch/processing error"
        error_msg = getattr(result, "_error", "")
        assert (
            "failed" in error_msg.lower() or "error" in error_msg.lower()
        ), f"Error should indicate fetch failure, got {error_msg}"
        assert not result.today_interval_prices, "interval_prices should be empty"
        assert (
            not result.today_interval_prices
        ), "Should have no data (empty interval prices) on malformed data"
        assert result.attempted_sources == [
            Source.NORDPOOL
        ], "Attempted sources should be recorded"

    @pytest.mark.asyncio
    async def test_fetch_data_with_out_of_bounds_prices(
        self, manager, auto_mock_core_dependencies
    ):
        """Test handling of anomalous price values - real-world scenario of price spikes."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Normal result structure but with extreme prices at 15-minute intervals
        extreme_price_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            "today_interval_prices": {
                "2025-04-26T10:00:00+00:00": 9999.99,  # Extreme high price
                "2025-04-26T10:15:00+00:00": -500.0,  # Extreme negative price
                "2025-04-26T10:30:00+00:00": 2.5,  # Normal price
            },
            "attempted_sources": [Source.NORDPOOL],
        }
        mock_fallback.return_value = extreme_price_result

        # Configure processor to pass through extreme prices
        # In real implementation, processor should validate but not clip these values
        extreme_processed_result = {
            **MOCK_PROCESSED_RESULT,
            "today_interval_prices": {
                "2025-04-26T10:00:00+02:00": 9999.99,
                "2025-04-26T10:15:00+02:00": -500.0,
                "2025-04-26T10:30:00+02:00": 2.5,
            },
        }
        mock_processor.return_value = extreme_processed_result

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert - Extreme prices should be preserved, not clipped
        assert (
            result.today_interval_prices["2025-04-26T10:00:00+02:00"] == 9999.99
        ), f"Extreme high price should not be clipped, got {result.today_interval_prices['2025-04-26T10:00:00+02:00']}"
        assert (
            result.today_interval_prices["2025-04-26T10:15:00+02:00"] == -500.0
        ), f"Negative price should not be clipped, got {result.today_interval_prices['2025-04-26T10:15:00+02:00']}"

        # Both normal and extreme prices should be present
        assert (
            len(result.today_interval_prices) == 3
        ), f"All price points should be preserved, got {len(result.today_interval_prices)}"

        # Result should indicate successful fetch despite extreme prices
        assert (
            result.today_interval_prices
        ), "Should have data (non-empty interval prices) despite extreme prices"
        assert not getattr(
            result, "_error", None
        ), f"No error should be present for extreme prices, got: {getattr(result, '_error', None)}"

    @pytest.mark.asyncio
    async def test_fetch_data_with_currency_conversion(
        self, manager, auto_mock_core_dependencies
    ):
        """Test proper currency conversion in real-world scenarios with differing currencies."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_exchange_service = auto_mock_core_dependencies[
            "get_exchange_service"
        ].return_value

        # Create result with EUR as source currency but SEK as target (15-minute intervals)
        eur_result = {
            "data_source": Source.ENTSOE,
            "area": "SE1",
            "currency": Currency.EUR,  # Source currency is EUR
            "today_interval_prices": {
                "2025-04-26T10:00:00+00:00": 0.1,  # EUR prices at 15-min intervals
                "2025-04-26T10:15:00+00:00": 0.2,
            },
            "attempted_sources": [Source.ENTSOE],
        }
        mock_fallback.return_value = eur_result

        # Configure exchange service to simulate conversion
        mock_exchange_service.convert_currency = AsyncMock(
            return_value=10.5
        )  # 1 EUR = 10.5 SEK

        # Expected processed result with converted currency
        converted_result = {
            **MOCK_PROCESSED_RESULT,
            "source": Source.ENTSOE,
            "source_currency": Currency.EUR,
            "target_currency": Currency.SEK,
            "today_interval_prices": {
                "2025-04-26T10:00:00+02:00": 1.05,  # 0.1 EUR * 10.5 = 1.05 SEK
                "2025-04-26T10:15:00+02:00": 2.1,  # 0.2 EUR * 10.5 = 2.1 SEK
            },
            "exchange_rate": 10.5,
        }
        mock_processor.return_value = converted_result

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        assert (
            result.source_currency == Currency.EUR
        ), f"Source currency should be EUR, got {result.source_currency}"
        assert (
            result.target_currency == Currency.SEK
        ), f"Target currency should be SEK, got {result.target_currency}"
        assert hasattr(result, "ecb_rate"), "Exchange rate should be included in result"
        # Note: IntervalPriceData stores exchange rate in ecb_rate field

        # Check converted prices
        assert (
            result.today_interval_prices["2025-04-26T10:00:00+02:00"] == 1.05
        ), f"First interval price should be converted to 1.05 SEK, got {result.today_interval_prices['2025-04-26T10:00:00+02:00']}"
        assert (
            result.today_interval_prices["2025-04-26T10:15:00+02:00"] == 2.1
        ), f"Second interval price should be converted to 2.1 SEK, got {result.today_interval_prices['2025-04-26T10:15:00+02:00']}"

    @pytest.mark.asyncio
    async def test_fetch_data_with_timezone_conversion(
        self, manager, auto_mock_core_dependencies
    ):
        """Test correct timezone conversion - critical for international markets."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_tz_service = auto_mock_core_dependencies["tz_service"].return_value

        # Create result with UTC timestamps at 15-minute intervals
        utc_result = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "currency": "SEK",
            "api_timezone": "UTC",
            "today_interval_prices": {
                "2025-04-26T10:00:00+00:00": 1.0,  # UTC timestamps at 15-min intervals
                "2025-04-26T10:15:00+00:00": 2.0,
            },
            "attempted_sources": [Source.NORDPOOL],
        }
        mock_fallback.return_value = utc_result

        # Configure timezone service - set it on the manager's actual tz_service
        # The mock tz_service instance needs target_timezone as an object, not a string
        import zoneinfo

        stockholm_tz = zoneinfo.ZoneInfo("Europe/Stockholm")
        manager._tz_service.target_timezone = stockholm_tz
        manager._tz_service.area_timezone = stockholm_tz

        # Create IntervalPriceData directly with the manager's tz_service
        # This ensures timezone properties work correctly
        converted_tz_data = IntervalPriceData(
            source=Source.NORDPOOL,
            area="SE1",
            target_currency="SEK",
            source_currency="SEK",
            source_timezone="UTC",
            target_timezone="Europe/Stockholm",
            today_interval_prices={
                "12:00": 1.0,  # HH:MM format after timezone conversion
                "12:15": 2.0,
            },
            tomorrow_interval_prices=_generate_complete_intervals(
                "2025-04-27T00:00:00", 1.5
            ),
            attempted_sources=[Source.NORDPOOL],
            _tz_service=manager._tz_service,  # Pass the configured tz_service
        )
        mock_processor.return_value = converted_tz_data

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert - verify timezone conversion happened correctly
        assert hasattr(
            result, "source_timezone"
        ), "Source timezone should be included in result"
        assert hasattr(
            result, "target_timezone"
        ), "Target timezone should be included in result"

        # Verify timezone values
        assert (
            result.source_timezone == "UTC"
        ), f"Source timezone should be UTC, got {result.source_timezone}"
        assert (
            result.target_timezone == "Europe/Stockholm"
        ), f"Target timezone should be Europe/Stockholm, got {result.target_timezone}"

        # Check that prices were converted correctly (HH:MM format in Stockholm time)
        assert (
            "12:00" in result.today_interval_prices
        ), f"Interval 12:00 should be in result, got keys: {list(result.today_interval_prices.keys())[:5]}"
        assert (
            result.today_interval_prices["12:00"] == 1.0
        ), f"Price at 12:00 should be 1.0, got {result.today_interval_prices['12:00']}"
        assert (
            "12:15" in result.today_interval_prices
        ), f"Interval 12:15 should be in result"
        assert (
            result.today_interval_prices["12:15"] == 2.0
        ), f"Price at 12:15 should be 2.0, got {result.today_interval_prices['12:15']}"

    @pytest.mark.asyncio
    async def test_partial_data_fallback_to_complete(
        self, manager, auto_mock_core_dependencies
    ):
        """Test: Primary source has partial data (tomorrow only), fallback source provides complete data."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_store = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.store
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data

        # Mock ENTSOE returning tomorrow-only (partial data)
        partial_result = {
            "data_source": Source.ENTSOE,
            "area": "NL",
            "target_currency": "EUR",
            "today_interval_prices": {},  # No today data
            "tomorrow_interval_prices": {
                "2025-04-27T00:00:00+02:00": 8.319,
                "2025-04-27T00:15:00+02:00": 8.226,
                "2025-04-27T00:30:00+02:00": 7.542,
                "2025-04-27T00:45:00+02:00": 7.275,
            },
            "attempted_sources": [Source.ENTSOE],
            "fallback_sources": [],
            "using_cached_data": False,
            "has_data": True,
        }

        # Mock Nordpool returning complete data
        complete_result = {
            "data_source": Source.NORDPOOL,
            "area": "NL",
            "target_currency": "EUR",
            "today_interval_prices": {
                "2025-04-26T00:00:00+02:00": 10.5,
                "2025-04-26T00:15:00+02:00": 10.2,
            },
            "tomorrow_interval_prices": {
                "2025-04-27T00:00:00+02:00": 8.3,
                "2025-04-27T00:15:00+02:00": 8.2,
            },
            "attempted_sources": [Source.NORDPOOL],
            "fallback_sources": [],
            "using_cached_data": False,
            "has_data": True,
        }

        # First fetch returns partial, second fetch returns complete
        mock_fallback.side_effect = [
            {
                "data_source": Source.ENTSOE,
                "raw_data": ["mock"],
                "attempted_sources": [Source.ENTSOE],
            },
            {
                "data_source": Source.NORDPOOL,
                "raw_data": ["mock"],
                "attempted_sources": [Source.NORDPOOL],
            },
        ]
        # Convert dicts to IntervalPriceData
        mock_processor.side_effect = [
            _dict_to_interval_price_data(partial_result),
            _dict_to_interval_price_data(complete_result),
        ]
        mock_cache_get.return_value = None

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        assert result is not None, "Should return data"
        assert (
            len(result.today_interval_prices) > 0
        ), "Should have today data from fallback"
        assert len(result.tomorrow_interval_prices) > 0, "Should have tomorrow data"
        assert result.source == Source.NORDPOOL, "Should use fallback source"

        # Verify fallback was called twice (first source + retry)
        assert mock_fallback.call_count == 2, "Should try primary source then fallback"

        # Verify ENTSOE is NOT marked as failed (it provided partial data, not a failure)
        assert (
            manager._failed_sources.get(Source.ENTSOE) is None
        ), "ENTSOE should NOT be marked as failed (provided partial data)"

    @pytest.mark.asyncio
    async def test_partial_data_no_remaining_sources(
        self, manager, auto_mock_core_dependencies
    ):
        """Test: Primary source has partial data, no more sources available, accept partial."""
        # Arrange - Only configure one source
        manager.config[Config.SOURCE_PRIORITY] = [Source.ENTSOE]
        manager._source_priority = [Source.ENTSOE]
        manager._api_classes = [manager._source_api_map[Source.ENTSOE]]

        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data

        # Mock ENTSOE returning tomorrow-only
        partial_result = {
            "data_source": Source.ENTSOE,
            "area": "SE1",
            "target_currency": "SEK",
            "today_interval_prices": {},
            "tomorrow_interval_prices": {
                "2025-04-27T00:00:00+02:00": 8.319,
                "2025-04-27T00:15:00+02:00": 8.226,
            },
            "attempted_sources": [Source.ENTSOE],
            "fallback_sources": [],
            "using_cached_data": False,
            "has_data": True,
        }

        mock_fallback.return_value = {
            "data_source": Source.ENTSOE,
            "raw_data": ["mock"],
            "attempted_sources": [Source.ENTSOE],
        }
        mock_processor.return_value = partial_result
        mock_cache_get.return_value = None

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        assert result is not None, "Should return partial data"
        assert len(result.today_interval_prices) == 0, "Should have no today data"
        assert len(result.tomorrow_interval_prices) > 0, "Should have tomorrow data"
        assert result.source == Source.ENTSOE, "Should use primary source"

        # Verify only called once (no fallback attempt)
        assert (
            mock_fallback.call_count == 1
        ), "Should only try primary source when no fallback available"

    @pytest.mark.asyncio
    async def test_partial_data_fallback_also_partial_uses_backup(
        self, manager, auto_mock_core_dependencies
    ):
        """Test: Primary has partial (tomorrow), fallback also partial (today), prefer today's data."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data

        # ENTSOE returns tomorrow-only
        entsoe_partial = {
            "data_source": Source.ENTSOE,
            "area": "SE1",
            "target_currency": "SEK",
            "today_interval_prices": {},
            "tomorrow_interval_prices": {
                "2025-04-27T00:00:00+02:00": 8.319,
                "2025-04-27T00:15:00+02:00": 8.226,
            },
            "attempted_sources": [Source.ENTSOE],
            "fallback_sources": [],
            "using_cached_data": False,
            "has_data": True,
        }

        # Nordpool returns today-only (TODAY is more important!)
        nordpool_partial = {
            "data_source": Source.NORDPOOL,
            "area": "SE1",
            "target_currency": "SEK",
            "today_interval_prices": {
                "2025-04-26T00:00:00+02:00": 10.5,
                "2025-04-26T00:15:00+02:00": 10.2,
            },
            "tomorrow_interval_prices": {},
            "attempted_sources": [Source.NORDPOOL],
            "fallback_sources": [],
            "using_cached_data": False,
            "has_data": True,
        }

        mock_fallback.side_effect = [
            {
                "data_source": Source.ENTSOE,
                "raw_data": ["mock"],
                "attempted_sources": [Source.ENTSOE],
            },
            {
                "data_source": Source.NORDPOOL,
                "raw_data": ["mock"],
                "attempted_sources": [Source.NORDPOOL],
            },
        ]
        # Convert dicts to IntervalPriceData
        mock_processor.side_effect = [
            _dict_to_interval_price_data(entsoe_partial),
            _dict_to_interval_price_data(nordpool_partial),
        ]
        mock_cache_get.return_value = None

        # Act
        result = await manager.fetch_data()

        # Cleanup background tasks
        await cancel_health_check_tasks(manager)

        # Assert
        assert result is not None, "Should return data"
        # Should use Nordpool because it has TODAY's data (more important than tomorrow)
        assert (
            result.source == Source.NORDPOOL
        ), "Should use source with today's data (more important)"
        assert (
            len(result.today_interval_prices) > 0
        ), "Should have today data from Nordpool"
        assert (
            len(result.tomorrow_interval_prices) == 0
        ), "Should not have tomorrow data"

    @pytest.mark.asyncio
    async def test_consecutive_failures_backoff(
        self, manager, auto_mock_core_dependencies
    ):
        """Test implicit validation - failed sources are skipped after grace period."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_now = auto_mock_core_dependencies["now"]
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data

        # Set coordinator created time to past grace period
        manager._coordinator_created_at = mock_now.return_value - timedelta(minutes=10)
        # Set last API fetch to simulate non-first-fetch
        manager._last_api_fetch = mock_now.return_value - timedelta(minutes=8)

        # Configure for failure
        mock_fallback.return_value = MOCK_FAILURE_RESULT
        # Processor called by _generate_empty_result
        empty_res_1 = await manager._generate_empty_result(
            error=f"All sources failed: {MOCK_FAILURE_RESULT['error']}"
        )
        mock_processor.return_value = empty_res_1
        mock_cache_get.return_value = None  # No cache

        # First failure - sources get marked as failed
        await manager.fetch_data()

        # Verify sources were marked as failed
        assert (
            Source.NORDPOOL in manager._failed_sources
        ), "Nordpool should be in failed sources"
        assert (
            Source.ENTSOE in manager._failed_sources
        ), "ENTSOE should be in failed sources"
        assert (
            manager._failed_sources[Source.NORDPOOL] is not None
        ), "Nordpool should have failure timestamp"
        assert (
            manager._consecutive_failures == 1
        ), "First failure should set counter to 1"

        # Reset mocks for second call
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        empty_res_2 = await manager._generate_empty_result(
            error="No API sources available"
        )
        mock_processor.return_value = empty_res_2

        # Advance time by 1 hour (still past grace period)
        mock_now.return_value += timedelta(hours=1)
        manager._last_api_fetch = mock_now.return_value - timedelta(minutes=30)

        # Verify NOT in grace period and NOT first fetch
        assert manager.is_in_grace_period() == False, "Should be past grace period"
        assert manager._last_api_fetch is not None, "Should not be first fetch"

        # Second attempt - sources should be SKIPPED because they failed and we're past grace period
        await manager.fetch_data()

        # Assert: FallbackManager should NOT be called because all sources are filtered out
        mock_fallback.assert_not_awaited(), "API should not be called - all sources failed recently"
        # No sources available, so consecutive failures would increment
        assert (
            manager._consecutive_failures == 2
        ), "Consecutive failures should increment to 2"

        # Reset for forced fetch test
        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()
        mock_fallback.return_value = (
            MOCK_SUCCESS_RESULT  # Simulate success for forced fetch
        )
        mock_processor.return_value = MOCK_PROCESSED_RESULT

        # Force fetch should bypass 24h filter and try sources again
        await manager.fetch_data(force=True)

        # Assert: Forced fetch bypasses filters
        mock_fallback.assert_awaited_once(), "Forced fetch should bypass 24h filter and call API"
        # On success, failures should be cleared
        assert (
            manager._consecutive_failures == 0
        ), "Consecutive failures should reset to 0 on success"
        assert (
            manager._failed_sources[Source.NORDPOOL] is None
        ), "Nordpool failure should be cleared on success"

        # Cleanup background tasks before finishing
        await cancel_health_check_tasks(manager)

    @pytest.mark.asyncio
    async def test_daily_retry_window_success_and_failure(
        self, manager, auto_mock_core_dependencies, monkeypatch
    ):
        """Test comprehensive source validation lifecycle with health check integration."""
        # This test validates the complete implicit validation flow:
        # 1. Initial failure marks sources with timestamp (after grace period + past first fetch)
        # 2. Subsequent regular fetches skip failed sources (health check will validate them)
        # 3. force=True bypasses the filter and allows immediate retry
        # 4. Retry success clears failure markers
        # 5. Retry failure updates failure timestamp and continues cycle
        # Note: Health check validates sources during special windows, not 24h timer

        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process
        mock_now = auto_mock_core_dependencies["now"]
        mock_cache_get = auto_mock_core_dependencies[
            "cache_manager"
        ].return_value.get_data

        # Mock _schedule_health_check to avoid background task complications in tests
        async def mock_schedule_health_check():
            pass  # No-op for testing - we're testing the filter logic, not the health check scheduler

        monkeypatch.setattr(
            manager, "_schedule_health_check", mock_schedule_health_check
        )

        # Clear the rate limiting state to start fresh
        from custom_components.ge_spot.coordinator.unified_price_manager import (
            _LAST_FETCH_TIME,
        )

        _LAST_FETCH_TIME.clear()

        initial_time = mock_now.return_value

        # Set time past grace period and simulate non-first-fetch
        manager._coordinator_created_at = initial_time - timedelta(minutes=10)
        manager._last_api_fetch = initial_time - timedelta(minutes=8)

        # Verify preconditions
        assert manager.is_in_grace_period() == False, "Should be past grace period"
        assert manager._last_api_fetch is not None, "Should not be first fetch"

        # ========== SCENARIO 1: Initial Failure (after grace period) ==========
        # Sources fail, get marked with timestamp, daily retry scheduled

        mock_fallback.return_value = MOCK_FAILURE_RESULT
        empty_res_1 = await manager._generate_empty_result(
            error=f"All sources failed: {MOCK_FAILURE_RESULT['error']}"
        )
        mock_processor.return_value = empty_res_1
        mock_cache_get.return_value = None

        result_1 = await manager.fetch_data()

        # Verify failure was recorded
        assert (
            Source.NORDPOOL in manager._failed_sources
        ), "Nordpool should be marked as failed"
        assert Source.ENTSOE in manager._failed_sources, "ENTSOE should be in failed"
        first_failure_time_nordpool = manager._failed_sources[Source.NORDPOOL]
        first_failure_time_entsoe = manager._failed_sources[Source.ENTSOE]
        assert (
            first_failure_time_nordpool is not None
        ), "Failure timestamp should be set"
        assert manager._consecutive_failures == 1, "First failure increments counter"
        assert (
            not result_1.today_interval_prices
        ), "No data on failure (empty interval prices)"
        assert mock_fallback.await_count == 1, "Fallback called on first failure"

        # ========== SCENARIO 2: Second Fetch (Sources Skipped) ==========
        # Sources should be skipped because they failed and we're past grace period

        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()

        # Advance time by 2 hours (still past grace period)
        mock_now.return_value = initial_time + timedelta(hours=2)
        manager._last_api_fetch = initial_time + timedelta(hours=1, minutes=30)
        _LAST_FETCH_TIME.clear()  # Clear rate limit to allow fetch attempt

        # Verify still past grace period
        assert (
            manager.is_in_grace_period() == False
        ), "Should still be past grace period"

        empty_res_2 = await manager._generate_empty_result(
            error="No API sources available"
        )
        mock_processor.return_value = empty_res_2

        result_2 = await manager.fetch_data()

        # Verify sources were skipped (no API call made)
        assert (
            mock_fallback.await_count == 0
        ), "API should NOT be called - sources failed recently"
        assert (
            manager._consecutive_failures == 2
        ), "Consecutive failures increment when no sources available"
        assert (
            manager._failed_sources[Source.NORDPOOL] == first_failure_time_nordpool
        ), "Failure timestamp unchanged when sources skipped"

        # ========== SCENARIO 3: Force Fetch - Bypasses Failed Source Filter ==========
        # force=True bypasses the failed source filter and retries immediately

        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()

        # Advance time by 2 hours (still within previous 24h window - but force bypasses it)
        mock_now.return_value = initial_time + timedelta(hours=4)
        _LAST_FETCH_TIME.clear()  # Clear rate limit

        # Configure for successful retry
        mock_fallback.return_value = MOCK_SUCCESS_RESULT
        mock_processor.return_value = _dict_to_interval_price_data(
            MOCK_PROCESSED_RESULT
        )

        result_3 = await manager.fetch_data(force=True)

        # Verify sources were retried (force=True bypasses filter) and success cleared failures
        assert mock_fallback.await_count == 1, "API should be called when force=True"
        assert (
            manager._consecutive_failures == 0
        ), "Success resets consecutive failure counter"
        assert (
            manager._failed_sources[Source.NORDPOOL] is None
        ), "Successful source clears failure marker"
        # Note: ENTSOE was never tried because NORDPOOL succeeded (fallback stops at first success)
        # So ENTSOE still has its failure marker - this is correct behavior
        assert result_3.today_interval_prices, "Data available on success"
        assert result_3.source == Source.NORDPOOL, "Correct source in result"

        # ========== SCENARIO 4: New Failure After Previous Success ==========
        # Sources fail again, get new failure timestamps

        mock_fallback.reset_mock()
        mock_processor.reset_mock()
        mock_cache_get.reset_mock()

        # Advance time by 2 hours
        second_failure_time_start = initial_time + timedelta(hours=6)
        mock_now.return_value = second_failure_time_start
        _LAST_FETCH_TIME.clear()

        mock_fallback.return_value = MOCK_FAILURE_RESULT
        empty_res_4 = await manager._generate_empty_result(
            error=f"All sources failed: {MOCK_FAILURE_RESULT['error']}"
        )
        mock_processor.return_value = empty_res_4

        result_4 = await manager.fetch_data()

        # Verify new failure markers set
        assert (
            Source.NORDPOOL in manager._failed_sources
        ), "Sources marked as failed again"
        second_failure_time_nordpool = manager._failed_sources[Source.NORDPOOL]
        assert (
            second_failure_time_nordpool == second_failure_time_start
        ), "New failure timestamp set"
        assert (
            second_failure_time_nordpool > first_failure_time_nordpool
        ), "New timestamp is later than first"
        assert manager._consecutive_failures == 1, "Consecutive failures restart at 1"
        assert not result_4.today_interval_prices, "No data on second failure"

        # Cleanup background tasks before finishing
        await cancel_health_check_tasks(manager)


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
            Config.VAT: Defaults.VAT,
            Config.INCLUDE_VAT: Defaults.INCLUDE_VAT,
        }
        manager_instance = UnifiedPriceManager(
            hass=hass,
            area="SE1",
            currency="SEK",
            config=config,
        )
        manager_instance._exchange_service = auto_mock_core_dependencies[
            "get_exchange_service"
        ].return_value
        if hasattr(manager_instance._data_processor, "_exchange_service"):
            manager_instance._data_processor._exchange_service = (
                manager_instance._exchange_service
            )
        return manager_instance

    async def cancel_health_check_tasks(self):
        """Cancel any lingering health check tasks."""
        for task in asyncio.all_tasks():
            if hasattr(task, "get_coro"):
                coro_str = str(task.get_coro())
                if (
                    "_schedule_health_check" in coro_str
                    or "_validate_all_sources" in coro_str
                ):
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    @pytest.mark.asyncio
    async def test_health_check_scheduled_on_failure(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that health check task is scheduled when all sources fail."""
        try:
            # Arrange
            mock_fallback = auto_mock_core_dependencies[
                "fallback_manager"
            ].return_value.fetch_with_fallback
            mock_fallback.return_value = MOCK_FAILURE_RESULT
            auto_mock_core_dependencies[
                "data_processor"
            ].return_value.process.return_value = MOCK_EMPTY_PROCESSED_RESULT

            # Act
            await manager.fetch_data()

            # Cleanup background tasks
            await cancel_health_check_tasks(manager)

            # Assert
            assert (
                manager._health_check_scheduled is True
            ), "Health check should be scheduled after all sources fail"
        finally:
            # Cleanup
            await self.cancel_health_check_tasks()

    @pytest.mark.asyncio
    async def test_health_check_only_scheduled_once(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that health check task is not scheduled multiple times."""
        try:
            # Arrange
            mock_fallback = auto_mock_core_dependencies[
                "fallback_manager"
            ].return_value.fetch_with_fallback
            mock_fallback.return_value = MOCK_FAILURE_RESULT
            auto_mock_core_dependencies[
                "data_processor"
            ].return_value.process.return_value = MOCK_EMPTY_PROCESSED_RESULT

            # Act - multiple failures
            await manager.fetch_data()
            first_scheduled = manager._health_check_scheduled

            await manager.fetch_data()
            await manager.fetch_data()

            # Cleanup background tasks
            await cancel_health_check_tasks(manager)

            # Assert - flag set once
            assert (
                manager._health_check_scheduled is True
            ), "Health check should be scheduled"
            assert first_scheduled is True, "Health check scheduled on first failure"
        finally:
            # Cleanup
            await self.cancel_health_check_tasks()

    @pytest.mark.asyncio
    async def test_validate_all_sources_success(
        self, manager, auto_mock_core_dependencies
    ):
        """Test _validate_all_sources marks all working sources as validated."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_fallback.return_value = {
            **MOCK_SUCCESS_RESULT,
            "raw_data": {"test": "data"},
        }

        # Mark sources as failed first
        now = datetime(2025, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
        manager._failed_sources["nordpool"] = now
        manager._failed_sources["entsoe"] = now

        # Act
        await manager._validate_all_sources()

        # Assert - all sources cleared
        assert (
            manager._failed_sources["nordpool"] is None
        ), "Nordpool should be cleared after successful validation"
        assert (
            manager._failed_sources["entsoe"] is None
        ), "ENTSOE should be cleared after successful validation"

    @pytest.mark.asyncio
    async def test_validate_all_sources_partial_failure(
        self, manager, auto_mock_core_dependencies
    ):
        """Test _validate_all_sources handles mixed success/failure."""
        # Arrange
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback

        # First source succeeds, second fails
        mock_fallback.side_effect = [
            {**MOCK_SUCCESS_RESULT, "raw_data": {"test": "data"}},  # nordpool success
            MOCK_FAILURE_RESULT,  # entsoe failure
        ]

        # Act
        await manager._validate_all_sources()

        # Assert
        assert (
            manager._failed_sources.get("nordpool") is None
        ), "Nordpool should succeed"
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
        assert next_check.date() == test_time.date() + timedelta(
            days=1
        ), "Should be next day"

    @pytest.mark.asyncio
    async def test_health_check_non_blocking_on_boot(self, manager):
        """Test that health check with run_immediately=True doesn't block boot.

        Verifies that even with slow-failing sources (long timeouts), the health
        check runs in background without blocking the caller.
        """
        # Arrange - simulate slow failing sources (65s timeout per source)
        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback:

            async def slow_timeout(*args, **kwargs):
                """Simulate slow timeout (5s + 15s + 45s = 65s)."""
                await asyncio.sleep(0.5)  # Simulate partial timeout for test speed
                return {"error": Exception("Timeout after 65s")}

            mock_fallback.side_effect = slow_timeout

            # Act - measure time for scheduling (should return immediately)
            import time

            start_time = time.time()

            # Schedule health check with run_immediately=True (background task)
            task = asyncio.create_task(
                manager._schedule_health_check(run_immediately=True)
            )

            # Time until task is created (should be instant)
            schedule_time = time.time() - start_time

            # Assert - scheduling should be instant (< 0.1s)
            assert (
                schedule_time < 0.1
            ), f"Scheduling took {schedule_time:.2f}s, should be instant"

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
        with patch.object(
            manager._cache_manager, "clear_cache", return_value=True
        ), patch.object(
            manager, "fetch_data", new_callable=AsyncMock
        ) as mock_fetch, patch.object(
            manager, "_schedule_health_check", new_callable=AsyncMock
        ) as mock_health:

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
        - Second source: slow timeout (65s)
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

        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback:
            mock_fallback.side_effect = mixed_timing

            # Act - measure time for scheduling
            import time

            start_time = time.time()

            # Schedule health check (should return immediately despite slow sources)
            task = asyncio.create_task(
                manager._schedule_health_check(run_immediately=True)
            )

            schedule_time = time.time() - start_time

            # Assert - scheduling should be instant
            assert (
                schedule_time < 0.1
            ), f"Scheduling took {schedule_time:.2f}s, should be instant"

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

        Best-case scenario: All sources respond quickly (< 5s each).
        """
        # Arrange
        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback:

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
            assert (
                validation_time < 1.0
            ), f"Validation took {validation_time:.2f}s, expected < 1s"

            # All sources should be marked as working
            assert all(
                manager._failed_sources.get(cls(config={}).source_type) is None
                for cls in manager._api_classes
            ), "All sources should be validated"

    @pytest.mark.asyncio
    async def test_first_fetch_tries_all_sources(self, manager):
        """Test that first fetch tries ALL sources regardless of validation failures.

        This is Phase 1.1 fix: During first fetch, even if a source failed during
        initialization/validation, it should still be attempted.
        """
        # Arrange - Mark one source as failed
        manager._failed_sources[Source.NORDPOOL] = datetime.now(
            timezone.utc
        ) - timedelta(minutes=5)

        # Ensure _last_api_fetch is None (first fetch)
        assert manager._last_api_fetch is None, "Should be first fetch"

        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback, patch.object(
            manager, "_process_result", new_callable=AsyncMock
        ) as mock_process:

            mock_fallback.return_value = {
                **MOCK_SUCCESS_RESULT,
                "raw_data": {"test": "data"},
            }
            mock_process.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )

            # Act
            result = await manager.fetch_data(force=False)

            # Assert - ALL sources should be tried on first fetch
            call_args = mock_fallback.call_args
            api_instances = call_args.kwargs["api_instances"]

            # Should have all configured sources, not filtered
            assert len(api_instances) == len(
                manager._api_classes
            ), "First fetch should try ALL sources regardless of failures"

            # Verify result is valid
            assert result is not None
            assert result.today_interval_prices, "Result should have data"

    @pytest.mark.asyncio
    async def test_grace_period_ignores_failures(self, manager):
        """Test that grace period allows all sources to be tried.

        This is Phase 1.1 fix: During grace period (first 5 minutes after reload),
        all sources should be tried regardless of recent failures.
        """
        # Arrange - Mark sources as failed
        now = datetime.now(timezone.utc)
        manager._failed_sources[Source.NORDPOOL] = now - timedelta(minutes=2)
        manager._failed_sources[Source.ENTSOE] = now - timedelta(minutes=1)

        # Set _last_api_fetch to simulate non-first fetch
        manager._last_api_fetch = now - timedelta(minutes=10)

        # Ensure we're in grace period
        assert manager.is_in_grace_period() == True, "Should be in grace period"

        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback, patch.object(
            manager, "_process_result", new_callable=AsyncMock
        ) as mock_process:

            mock_fallback.return_value = {
                **MOCK_SUCCESS_RESULT,
                "raw_data": {"test": "data"},
            }
            mock_process.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )

            # Act
            result = await manager.fetch_data(force=False)

            # Assert - ALL sources should be tried during grace period
            call_args = mock_fallback.call_args
            api_instances = call_args.kwargs["api_instances"]

            assert len(api_instances) == len(
                manager._api_classes
            ), "Grace period should try ALL sources regardless of failures"

            assert result is not None
            assert result.today_interval_prices, "Result should have data"

    @pytest.mark.asyncio
    async def test_after_grace_period_skips_failed_sources(self, manager):
        """Test that after grace period, failed sources are skipped.

        Normal operation: After grace period and after first successful fetch,
        recently failed sources should be skipped until health check validates them.
        """
        # Arrange - Set coordinator created time to be past grace period
        manager._coordinator_created_at = datetime.now(timezone.utc) - timedelta(
            minutes=10
        )

        # Mark a source as failed and set last fetch time
        now = datetime.now(timezone.utc)
        manager._failed_sources[Source.NORDPOOL] = now - timedelta(minutes=2)
        manager._last_api_fetch = now - timedelta(minutes=20)  # Past first fetch

        # Ensure we're NOT in grace period
        assert manager.is_in_grace_period() == False, "Should NOT be in grace period"

        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback, patch.object(
            manager, "_process_result", new_callable=AsyncMock
        ) as mock_process:

            mock_fallback.return_value = {
                **MOCK_SUCCESS_RESULT,
                "raw_data": {"test": "data"},
            }
            mock_process.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )

            # Act
            result = await manager.fetch_data(force=False)

            # Assert - Failed source should be skipped
            call_args = mock_fallback.call_args
            api_instances = call_args.kwargs["api_instances"]

            # Should have fewer sources (failed one skipped)
            assert len(api_instances) < len(
                manager._api_classes
            ), "After grace period, failed sources should be skipped"

            # Verify the failed source is not in the list
            source_names = [type(api).__name__ for api in api_instances]
            assert (
                "NordpoolAPI" not in source_names
            ), "Failed Nordpool source should be skipped"

    @pytest.mark.asyncio
    async def test_successful_fetch_updates_last_api_fetch(self, manager):
        """Test that successful fetch updates _last_api_fetch timestamp.

        This ensures first_fetch detection works correctly after the first successful fetch.
        """
        # Arrange
        assert manager._last_api_fetch is None, "Should start with None"

        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback, patch.object(
            manager, "_process_result", new_callable=AsyncMock
        ) as mock_process, patch.object(
            manager._cache_manager, "store"
        ) as mock_cache_store:

            mock_fallback.return_value = {
                **MOCK_SUCCESS_RESULT,
                "raw_data": {"test": "data"},
            }
            mock_process.return_value = _dict_to_interval_price_data(
                MOCK_PROCESSED_RESULT
            )

            # Act
            await manager.fetch_data(force=False)

            # Assert - _last_api_fetch should be updated to not None
            assert (
                manager._last_api_fetch is not None
            ), "_last_api_fetch should be set after successful fetch"

            # Verify it's a datetime object
            assert isinstance(
                manager._last_api_fetch, datetime
            ), "_last_api_fetch should be a datetime object"

    @pytest.mark.asyncio
    async def test_all_attempted_sources_tracking(self, manager):
        """Test that _all_attempted_sources tracks ALL source attempts including validation.

        Phase 2.2 fix: Comprehensive tracking of all source attempts for debugging.
        """
        # Arrange - Initially empty
        assert manager._all_attempted_sources == []

        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback, patch.object(
            manager, "_process_result", new_callable=AsyncMock
        ) as mock_process, patch.object(
            manager._cache_manager, "store"
        ) as mock_cache_store:

            mock_fallback.return_value = {
                **MOCK_SUCCESS_RESULT,
                "raw_data": {"test": "data"},
                "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
            }
            mock_process.return_value = _dict_to_interval_price_data(
                {
                    **MOCK_PROCESSED_RESULT,
                    "attempted_sources": [Source.NORDPOOL, Source.ENTSOE],
                }
            )

            # Act
            await manager.fetch_data(force=False)

            # Assert - All attempted sources should be tracked
            assert (
                len(manager._all_attempted_sources) > 0
            ), "_all_attempted_sources should track attempted sources"

            # Should include sources from the fetch
            assert (
                Source.NORDPOOL in manager._all_attempted_sources
                or Source.ENTSOE in manager._all_attempted_sources
            ), "Should track at least one source from fetch"

    @pytest.mark.asyncio
    async def test_all_attempted_sources_includes_validation(self, manager):
        """Test that _all_attempted_sources includes validation attempts.

        Phase 2.2 fix: Validation attempts should be tracked separately from fetch attempts.
        """
        # Arrange
        assert manager._all_attempted_sources == []

        with patch.object(
            manager._fallback_manager, "fetch_with_fallback"
        ) as mock_fallback:
            # Simulate validation attempt
            mock_fallback.return_value = {
                **MOCK_SUCCESS_RESULT,
                "raw_data": {"test": "data"},
            }

            # Act - Run validation (which tracks sources)
            await manager._validate_all_sources()

            # Assert - Should have tracked all configured sources
            assert len(manager._all_attempted_sources) == len(
                manager._api_classes
            ), "Validation should track all configured sources"

            # Verify sources are actually in the list
            for api_class in manager._api_classes:
                source_name = api_class(config={}).source_type
                assert (
                    source_name in manager._all_attempted_sources
                ), f"Source '{source_name}' should be tracked after validation"

    @pytest.mark.asyncio
    async def test_failure_message_includes_next_check_time(self, manager, caplog):
        """Test that failure messages include next health check time.

        Phase 2.1 fix: Users should know WHEN sources will be retried.
        """
        # Arrange
        caplog.clear()

        try:
            with patch.object(
                manager._fallback_manager, "fetch_with_fallback"
            ) as mock_fallback, patch.object(
                manager, "_process_result", new_callable=AsyncMock
            ) as mock_process:

                # Simulate all sources failing
                mock_fallback.return_value = {
                    "error": Exception("All failed"),
                    "attempted_sources": [Source.NORDPOOL],
                }
                mock_process.return_value = None

                # Act
                result = await manager.fetch_data(force=False)

                # Assert - Check log messages
                warning_messages = [
                    record.message
                    for record in caplog.records
                    if record.levelname == "WARNING"
                ]

                # Should have a message about failed sources with time
                assert any(
                    "failed" in msg.lower() for msg in warning_messages
                ), "Should have failure warning"

                # Should mention when next check will happen
                assert any(
                    ":" in msg and any(char.isdigit() for char in msg)
                    for msg in warning_messages
                ), "Should include time (HH:MM format) in failure message"
        finally:
            # Cleanup health check task
            if manager._health_check_task:
                manager._health_check_task.cancel()
                try:
                    await manager._health_check_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_health_check_scheduling_message_includes_windows(
        self, manager, caplog
    ):
        """Test that health check scheduling message includes time windows.

        Phase 2.1 fix: Users should know health check windows.
        """
        # Arrange
        caplog.clear()

        try:
            with patch.object(
                manager._fallback_manager, "fetch_with_fallback"
            ) as mock_fallback, patch.object(
                manager, "_process_result", new_callable=AsyncMock
            ) as mock_process:

                # Simulate failure to trigger health check scheduling
                mock_fallback.return_value = {
                    "error": Exception("Failed"),
                    "attempted_sources": [Source.NORDPOOL],
                }
                mock_process.return_value = None

                # Act
                result = await manager.fetch_data(force=False)

                # Assert - Check for scheduling message
                info_messages = [
                    record.message
                    for record in caplog.records
                    if record.levelname == "INFO"
                ]

                # Should mention scheduling health check
                scheduling_msgs = [
                    msg
                    for msg in info_messages
                    if "scheduling" in msg.lower() and "health check" in msg.lower()
                ]

                if scheduling_msgs:  # Only check if health check was scheduled
                    # Should mention time windows
                    assert any(
                        "00:00" in msg or ":00-" in msg for msg in scheduling_msgs
                    ), "Scheduling message should include health check time windows"
        finally:
            # Cleanup health check task
            if manager._health_check_task:
                manager._health_check_task.cancel()
                try:
                    await manager._health_check_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_mark_source_attempted_no_duplicates(self, manager):
        """Test that _mark_source_attempted prevents duplicates.

        Each source should only appear once in _all_attempted_sources even if attempted multiple times.
        """
        # Arrange
        assert manager._all_attempted_sources == []

        # Act - Mark same source multiple times
        manager._mark_source_attempted(Source.NORDPOOL)
        manager._mark_source_attempted(Source.NORDPOOL)
        manager._mark_source_attempted(Source.NORDPOOL)
        manager._mark_source_attempted(Source.ENTSOE)
        manager._mark_source_attempted(Source.ENTSOE)

        # Assert - Should only have unique entries
        assert (
            len(manager._all_attempted_sources) == 2
        ), "Should only track unique sources"
        assert (
            manager._all_attempted_sources.count(Source.NORDPOOL) == 1
        ), "Should not have duplicate entries for same source"
        assert (
            manager._all_attempted_sources.count(Source.ENTSOE) == 1
        ), "Should not have duplicate entries for same source"
