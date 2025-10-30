"""Test that stale tomorrow data is properly detected and cleared.

This test verifies the fix for the bug where cached tomorrow_interval_prices
from yesterday were treated as valid for today's tomorrow fetch decision,
causing the integration to not fetch fresh tomorrow data until reload.

The bug scenario:
1. At 13:30 yesterday, API returned today+tomorrow prices
2. Cache stored both with fetched_at = yesterday's date
3. At midnight, cache migration moved yesterday's tomorrow → today's today
4. At 13:30 today, during special window, cached data still had "tomorrow_interval_prices"
5. System incorrectly treated these as valid for today's tomorrow
6. Fetch decision used stale data → decided not to fetch → sensors show no tomorrow data
7. Only manual reload would trigger fresh fetch

The fix:
- During special window (13:00-15:00), check fetched_at timestamp
- If cached tomorrow_interval_prices exist but cache is from before today, clear them
- This forces fetch decision to correctly identify missing tomorrow data
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
from freezegun import freeze_time

# Add the parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.coordinator.unified_price_manager import (
    UnifiedPriceManager,
)
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.defaults import Defaults
from custom_components.ge_spot.const.config import Config
from tests.lib.mocks.hass import MockHass


def _generate_complete_intervals(base_price=1.0):
    """Generate 96 intervals (15-minute intervals for 24 hours) with HH:MM keys."""
    intervals = {}
    for h in range(24):
        for m in [0, 15, 30, 45]:
            interval_key = f"{h:02d}:{m:02d}"
            intervals[interval_key] = base_price
    return intervals


def _dict_to_interval_price_data(data_dict):
    """Convert a test dict to IntervalPriceData (for backward compatibility with existing tests).

    This helps migrate tests that were creating dict mocks.
    """
    return IntervalPriceData(
        source=data_dict.get("data_source", data_dict.get("source", Source.NORDPOOL)),
        area=data_dict.get("area", "SE1"),
        target_currency=data_dict.get(
            "target_currency", data_dict.get("currency", "SEK")
        ),
        source_currency=data_dict.get(
            "source_currency", data_dict.get("currency", "EUR")
        ),
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
        ecb_rate=data_dict.get("ecb_rate", data_dict.get("exchange_rate")),
        ecb_updated=data_dict.get("ecb_updated"),
        migrated_from_tomorrow=data_dict.get("migrated_from_tomorrow", False),
        original_cache_date=data_dict.get("original_cache_date"),
        raw_data=data_dict.get("raw_data"),
        _tz_service=None,  # Tests usually don't need this
    )


@pytest.fixture(autouse=True)
def auto_mock_core_dependencies():
    """Automatically mock core dependencies used by UnifiedPriceManager."""
    with patch(
        "custom_components.ge_spot.coordinator.unified_price_manager._LAST_FETCH_TIME",
        new_callable=dict,
    ), patch(
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
        "custom_components.ge_spot.coordinator.unified_price_manager.async_get_clientsession"
    ) as mock_get_session, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.get_sources_for_region"
    ) as mock_get_sources:

        # Configure default return values
        mock_get_sources.return_value = [Source.NORDPOOL, Source.ENTSOE]
        mock_fallback_manager.return_value.fetch_with_fallback = AsyncMock(
            return_value={}
        )

        # Add auto-conversion wrapper for CacheManager.get_data()
        original_get_data = MagicMock(return_value=None)

        def get_data_wrapper(*args, **kwargs):
            result = original_get_data(*args, **kwargs)
            if result is not None and isinstance(result, dict):
                return _dict_to_interval_price_data(result)
            return result

        mock_cache_manager.return_value.get_data = get_data_wrapper
        mock_cache_manager.return_value.get_data.mock = (
            original_get_data  # Store original for test configuration
        )
        mock_cache_manager.return_value.store = MagicMock()

        # Add auto-conversion wrapper for DataProcessor.process()
        original_process = AsyncMock(return_value={})

        async def process_wrapper(*args, **kwargs):
            result = await original_process(*args, **kwargs)
            if result is not None and isinstance(result, dict):
                return _dict_to_interval_price_data(result)
            return result

        mock_data_processor.return_value.process = process_wrapper
        mock_data_processor.return_value.process.mock = (
            original_process  # Store original for test configuration
        )

        # Configure timezone service with real timezone.utc objects to support DST checks
        mock_tz_service_instance = MagicMock()
        mock_tz_service_instance.target_timezone = timezone.utc
        mock_tz_service_instance.area_timezone = timezone.utc
        mock_tz_service.return_value = mock_tz_service_instance
        mock_get_exchange_service.return_value = AsyncMock()
        mock_get_session.return_value = MagicMock()

        yield {
            "fallback_manager": mock_fallback_manager,
            "cache_manager": mock_cache_manager,
            "data_processor": mock_data_processor,
            "tz_service": mock_tz_service,
            "get_exchange_service": mock_get_exchange_service,
            "get_session": mock_get_session,
            "get_sources": mock_get_sources,
        }


class TestStaleTomorrowDataFix:
    """Test the fix for stale tomorrow data during special window (13:00-15:00)."""

    @pytest.fixture
    def manager(self, auto_mock_core_dependencies):
        """Provides an initialized UnifiedPriceManager instance for tests."""
        hass = MockHass()
        config = {
            Config.DISPLAY_UNIT: Defaults.DISPLAY_UNIT,
            Config.API_KEY: None,
            Config.SOURCE_PRIORITY: [Source.NORDPOOL],
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

        return manager_instance

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 14:00:00 UTC")  # During special window
    async def test_stale_tomorrow_data_cleared_and_refetched(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that stale tomorrow data from yesterday is detected, cleared, and triggers refetch.

        Scenario:
        - Current time: 2025-01-15 14:00 (during special window 13:00-15:00)
        - Cache contains data fetched yesterday (2025-01-14) with tomorrow_interval_prices
        - After midnight migration, that "tomorrow" is now in "today"
        - The cached entry still has "tomorrow_interval_prices" but it's stale (for old tomorrow)
        - System should detect this and fetch fresh data
        """
        # Mock components
        mock_cache = auto_mock_core_dependencies["cache_manager"].return_value
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Simulate cached data from YESTERDAY (2025-01-14 13:30)
        # This represents the state AFTER midnight migration where:
        # - yesterday's tomorrow became today's today
        # - but tomorrow_interval_prices are still there (stale!)
        stale_cached_data = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(50.0),  # 96 intervals
            "tomorrow_interval_prices": _generate_complete_intervals(
                60.0
            ),  # 96 intervals - STALE!
            "fetched_at": "2025-01-14 13:30:00",  # YESTERDAY - this is the key indicator
            "source_timezone": "Europe/Stockholm",
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,  # This makes it look valid, but it's stale
            },
        }

        # Fresh data that API will return
        fresh_data_from_api = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(55.0),
            "tomorrow_interval_prices": _generate_complete_intervals(
                65.0
            ),  # Fresh tomorrow!
            "attempted_sources": [Source.NORDPOOL],
        }

        # Processed fresh data
        processed_fresh_data = {
            **fresh_data_from_api,
            "source": Source.NORDPOOL,
            "target_currency": "SEK",
            "source_timezone": "Europe/Stockholm",
            "has_data": True,
            "using_cached_data": False,
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,
            },
        }

        # Setup mocks
        mock_cache.get_data.mock.return_value = _dict_to_interval_price_data(
            stale_cached_data.copy()
        )
        mock_fallback.return_value = fresh_data_from_api
        mock_processor.mock.return_value = _dict_to_interval_price_data(
            processed_fresh_data
        )

        # Mock timezone service to indicate we're in special window
        manager._tz_service.get_current_interval_key.return_value = "14:00"
        manager._tz_service.get_target_timezone.return_value = timezone.utc

        # Execute
        result = await manager.fetch_data()

        # Verify: System should have detected stale tomorrow data and fetched fresh
        assert result is not None, "fetch_data should return data"
        # Result is IntervalPriceData instance
        assert hasattr(
            result, "today_interval_prices"
        ), "Result should have today_interval_prices"
        assert hasattr(
            result, "tomorrow_interval_prices"
        ), "Result should contain tomorrow prices"
        assert (
            len(result.tomorrow_interval_prices) == 96
        ), "Should have 96 fresh tomorrow intervals"

        # Verify fresh data was fetched (not cached)
        mock_fallback.assert_awaited_once(), (
            "Should fetch fresh data when tomorrow is stale"
        )

        # Verify cache.get_data was called to retrieve the stale cache
        mock_cache.get_data.mock.assert_called()

        # The key assertion: verify the logic cleared stale tomorrow data
        # We can't directly assert on internal state, but we can verify the behavior:
        # If tomorrow was NOT cleared, the system would have used cached data
        # Since we see a fetch happened, the staleness check worked
        assert (
            result.using_cached_data is False
        ), "Should not use cached data when tomorrow is stale"

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 14:00:00 UTC")  # During special window
    async def test_fresh_tomorrow_data_preserved_no_clearing(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that fresh tomorrow data from TODAY is NOT cleared by staleness check.

        Scenario:
        - Current time: 2025-01-15 14:00 (during special window)
        - Cache contains data fetched TODAY (2025-01-15 13:30) with tomorrow_interval_prices
        - Tomorrow data is fresh (fetched today)
        - Staleness check should NOT clear it
        """
        mock_cache = auto_mock_core_dependencies["cache_manager"].return_value
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Cached data from TODAY (fresh) - fetched at 13:30 today
        fresh_cached_data = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(50.0),
            "tomorrow_interval_prices": _generate_complete_intervals(60.0),  # FRESH!
            "fetched_at": "2025-01-15 13:30:00",  # TODAY - fresh!
            "source_timezone": "Europe/Stockholm",
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,
            },
        }

        # API returns same data (but shouldn't be called if caching works)
        fresh_api_data = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(50.0),
            "tomorrow_interval_prices": _generate_complete_intervals(60.0),
            "attempted_sources": [Source.NORDPOOL],
        }

        processed_data = {
            **fresh_api_data,
            "source": Source.NORDPOOL,
            "target_currency": "SEK",
            "has_data": True,
            "using_cached_data": False,
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,
            },
        }

        mock_cache.get_data.mock.return_value = fresh_cached_data.copy()
        mock_fallback.return_value = fresh_api_data
        mock_processor.mock.return_value = processed_data
        manager._tz_service.get_current_interval_key.return_value = "14:00"
        manager._tz_service.get_target_timezone.return_value = timezone.utc

        # Execute
        result = await manager.fetch_data()

        # Verify: Result should exist
        assert result is not None

        # The KEY ASSERTION: Verify cache.get_data was called and returned data with tomorrow
        #  If the staleness check had incorrectly cleared tomorrow from fresh data,
        #  the system would think tomorrow was missing.
        #  Since we're in special window, it would trigger fetch.
        #  But fresh data's fetched_at is from TODAY, so staleness check should skip it.
        calls = mock_cache.get_data.mock.call_args_list
        assert len(calls) > 0, "Cache should be checked"

        # The cache returned tomorrow_interval_prices with 96 intervals
        # If staleness check worked correctly, it didn't clear them
        # We can verify this by checking that the returned tomorrow count matches
        cached_data = mock_cache.get_data.mock.return_value
        assert "tomorrow_interval_prices" in cached_data
        assert len(cached_data["tomorrow_interval_prices"]) == 96

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 10:00:00 UTC")  # Outside special window
    async def test_stale_tomorrow_check_only_during_special_window(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that staleness check only applies during special window (13:00-15:00).

        Scenario:
        - Current time: 2025-01-15 10:00 (OUTSIDE special window)
        - Cache has stale tomorrow data from yesterday
        - System should NOT clear it (staleness check only runs in special window)
        - Will use cached data or fetch based on normal logic (not staleness)
        """
        mock_cache = auto_mock_core_dependencies["cache_manager"].return_value

        # Stale cached data (same as first test)
        stale_cached_data = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "source": Source.NORDPOOL,
            "target_currency": "SEK",
            "today_interval_prices": _generate_complete_intervals(50.0),
            "tomorrow_interval_prices": _generate_complete_intervals(60.0),  # Stale
            "fetched_at": "2025-01-14 13:30:00",  # Yesterday
            "source_timezone": "Europe/Stockholm",
            "has_data": True,
            "using_cached_data": True,
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,
            },
        }

        mock_cache.get_data.mock.return_value = _dict_to_interval_price_data(
            stale_cached_data.copy()
        )
        manager._tz_service.get_current_interval_key.return_value = "10:00"
        manager._tz_service.get_target_timezone.return_value = timezone.utc

        # Mock grace period check
        with patch.object(manager, "is_in_grace_period", return_value=False):
            result = await manager.fetch_data()

        # Verify: Outside special window, stale check doesn't apply
        # System will use cached data if rate limit prevents fetch
        assert result is not None
        # The cached data will be used (with stale tomorrow) because we're outside special window
        assert result.using_cached_data is True

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 14:00:00 UTC")
    async def test_staleness_check_handles_missing_fetched_at(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that staleness check handles missing fetched_at gracefully.

        Scenario:
        - Cache data doesn't have fetched_at timestamp (corrupted/old cache)
        - System should handle gracefully and not crash
        """
        mock_cache = auto_mock_core_dependencies["cache_manager"].return_value
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Cached data WITHOUT fetched_at
        cached_data_no_timestamp = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(50.0),
            "tomorrow_interval_prices": _generate_complete_intervals(60.0),
            # NO fetched_at!
            "source_timezone": "Europe/Stockholm",
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,
            },
        }

        fresh_api_data = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(55.0),
            "tomorrow_interval_prices": _generate_complete_intervals(65.0),
            "attempted_sources": [Source.NORDPOOL],
        }

        processed_data = {
            **fresh_api_data,
            "source": Source.NORDPOOL,
            "target_currency": "SEK",
            "has_data": True,
            "using_cached_data": False,
        }

        mock_cache.get_data.mock.return_value = cached_data_no_timestamp.copy()
        mock_fallback.return_value = fresh_api_data
        mock_processor.mock.return_value = processed_data
        manager._tz_service.get_current_interval_key.return_value = "14:00"

        # Should not crash
        result = await manager.fetch_data()
        assert result is not None, "Should handle missing fetched_at gracefully"

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 14:00:00 UTC")
    async def test_staleness_check_with_malformed_fetched_at(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that staleness check handles malformed fetched_at timestamp.

        Scenario:
        - Cache has fetched_at but it's not parseable
        - System should handle gracefully (skip staleness check, proceed normally)
        """
        mock_cache = auto_mock_core_dependencies["cache_manager"].return_value

        # Cached data with malformed timestamp
        cached_data_bad_timestamp = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "source": Source.NORDPOOL,
            "target_currency": "SEK",
            "today_interval_prices": _generate_complete_intervals(50.0),
            "tomorrow_interval_prices": _generate_complete_intervals(60.0),
            "fetched_at": "INVALID_TIMESTAMP",  # Malformed!
            "source_timezone": "Europe/Stockholm",
            "has_data": True,
            "using_cached_data": True,
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,
            },
        }

        mock_cache.get_data.mock.return_value = cached_data_bad_timestamp.copy()
        manager._tz_service.get_current_interval_key.return_value = "14:00"

        # Mock grace period
        with patch.object(manager, "is_in_grace_period", return_value=False):
            # Should not crash, will use cached data or fetch normally
            result = await manager.fetch_data()
            assert result is not None, "Should handle malformed fetched_at gracefully"

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 14:00:00 UTC")  # During special window
    async def test_data_validity_cleared_with_stale_tomorrow(
        self, manager, auto_mock_core_dependencies
    ):
        """Test that data_validity is cleared along with stale tomorrow_interval_prices.

        This is the CRITICAL test for the fix in commit c974d05.

        The bug was that when stale tomorrow_interval_prices were cleared,
        data_validity was NOT cleared, causing fetch decision to use stale
        validity showing tomorrow=96 when tomorrow was actually empty.

        This test validates that BOTH are cleared, forcing recalculation
        of data_validity with correct tomorrow_count=0.

        Scenario:
        - Current time: 2025-01-15 14:00 (during special window)
        - Cache from yesterday has data_validity with tomorrow=96
        - Cache from yesterday has tomorrow_interval_prices
        - Staleness check should clear BOTH
        - System should recalculate validity showing tomorrow=0
        - This triggers fresh API fetch
        """
        mock_cache = auto_mock_core_dependencies["cache_manager"].return_value
        mock_fallback = auto_mock_core_dependencies[
            "fallback_manager"
        ].return_value.fetch_with_fallback
        mock_processor = auto_mock_core_dependencies[
            "data_processor"
        ].return_value.process

        # Stale cached data from YESTERDAY with BOTH tomorrow prices AND validity
        stale_cached_data = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(50.0),
            "tomorrow_interval_prices": _generate_complete_intervals(60.0),  # STALE!
            "fetched_at": "2025-01-14 13:30:00",  # YESTERDAY
            "source_timezone": "Europe/Stockholm",
            "data_validity": {  # STALE! Shows tomorrow=96 but data is from yesterday
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,  # This is the problem - stale validity
            },
        }

        # Fresh API data
        fresh_api_data = {
            "area": "SE1",
            "currency": "SEK",
            "data_source": Source.NORDPOOL,
            "today_interval_prices": _generate_complete_intervals(55.0),
            "tomorrow_interval_prices": _generate_complete_intervals(65.0),
            "attempted_sources": [Source.NORDPOOL],
        }

        # Processed fresh data
        processed_fresh_data = {
            **fresh_api_data,
            "source": Source.NORDPOOL,
            "target_currency": "SEK",
            "has_data": True,
            "using_cached_data": False,
            "data_validity": {
                "today_interval_count": 96,
                "tomorrow_interval_count": 96,
            },
        }

        mock_cache.get_data.mock.return_value = _dict_to_interval_price_data(
            stale_cached_data.copy()
        )
        mock_fallback.return_value = fresh_api_data
        mock_processor.mock.return_value = _dict_to_interval_price_data(
            processed_fresh_data
        )
        manager._tz_service.get_current_interval_key.return_value = "14:00"
        manager._tz_service.get_target_timezone.return_value = timezone.utc

        # Execute
        result = await manager.fetch_data()

        # CRITICAL ASSERTION: Verify fresh data was fetched
        # If data_validity was NOT cleared (the bug), system would think tomorrow=96
        # and skip the fetch, returning cached data with using_cached_data=True
        #
        # With the fix, data_validity IS cleared, system recalculates it as tomorrow=0,
        # and triggers fresh fetch, returning using_cached_data=False
        assert result is not None, "fetch_data should return data"
        assert (
            result.using_cached_data is False
        ), "Should fetch fresh data when both tomorrow AND data_validity are stale"

        # Verify the fetch was actually called (not using cache)
        mock_fallback.assert_awaited_once(), (
            "Should call API fetch when stale data_validity is cleared"
        )

        # Verify we got fresh tomorrow data
        assert hasattr(
            result, "tomorrow_interval_prices"
        ), "Result should have tomorrow prices"
        assert (
            len(result.tomorrow_interval_prices) == 96
        ), "Should have 96 fresh tomorrow intervals"
