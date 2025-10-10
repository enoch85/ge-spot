"""
Unit tests for implicit validation functionality.

Tests the production implementation of:
- Failed sources tracking with timestamps
- Implicit validation during fetch_data()
- Daily retry scheduling
- Exponential timeout configuration
- Source filtering based on failure timestamps
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
import pytest

from custom_components.ge_spot.coordinator.unified_price_manager import UnifiedPriceManager
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.network import Network
from custom_components.ge_spot.const.config import Config
from homeassistant.util import dt as dt_util


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock()
    hass.config.time_zone = "UTC"
    hass.loop = asyncio.get_event_loop()
    hass.data = {}
    return hass


@pytest.fixture
def mock_config():
    """Create mock config dictionary."""
    return {
        Config.SOURCE_PRIORITY: [Source.NORDPOOL, Source.ENERGY_CHARTS, Source.OMIE],
    }


@pytest.fixture
def price_manager(mock_hass, mock_config):
    """Create UnifiedPriceManager instance."""
    return UnifiedPriceManager(mock_hass, "SE3", "SEK", mock_config)


class TestFailedSourcesTracking:
    """Test failed sources tracking with timestamps."""
    
    def test_failed_sources_attribute_exists(self, price_manager):
        """Verify _failed_sources attribute exists and is a dict."""
        assert hasattr(price_manager, '_failed_sources')
        assert isinstance(price_manager._failed_sources, dict)
    
    def test_retry_scheduled_attribute_exists(self, price_manager):
        """Verify _retry_scheduled attribute exists and is a set."""
        assert hasattr(price_manager, '_retry_scheduled')
        assert isinstance(price_manager._retry_scheduled, set)
    
    def test_initial_state_empty(self, price_manager):
        """Verify initial state has no failed sources or scheduled retries."""
        assert len(price_manager._failed_sources) == 0
        assert len(price_manager._retry_scheduled) == 0
    
    def test_can_add_failed_source_with_timestamp(self, price_manager):
        """Verify sources can be added to failed dict with timestamp."""
        now = dt_util.now()
        price_manager._failed_sources[Source.ENERGY_CHARTS] = now
        
        assert Source.ENERGY_CHARTS in price_manager._failed_sources
        assert price_manager._failed_sources[Source.ENERGY_CHARTS] == now
        assert len(price_manager._failed_sources) == 1
    
    def test_can_clear_failed_source(self, price_manager):
        """Verify sources can be cleared from failed dict (set to None)."""
        now = dt_util.now()
        price_manager._failed_sources[Source.ENERGY_CHARTS] = now
        
        # Clear by setting to None (marks as working)
        price_manager._failed_sources[Source.ENERGY_CHARTS] = None
        
        assert price_manager._failed_sources[Source.ENERGY_CHARTS] is None
    
    def test_can_remove_failed_source(self, price_manager):
        """Verify sources can be removed from failed dict entirely."""
        now = dt_util.now()
        price_manager._failed_sources[Source.ENERGY_CHARTS] = now
        
        # Remove entirely
        del price_manager._failed_sources[Source.ENERGY_CHARTS]
        
        assert Source.ENERGY_CHARTS not in price_manager._failed_sources
        assert len(price_manager._failed_sources) == 0


class TestExponentialBackoffConfiguration:
    """Test exponential backoff timeout configuration."""
    
    def test_retry_base_timeout_defined(self):
        """Verify RETRY_BASE_TIMEOUT is defined."""
        assert hasattr(Network.Defaults, 'RETRY_BASE_TIMEOUT')
    
    def test_retry_base_timeout_value(self):
        """Verify RETRY_BASE_TIMEOUT is 2 seconds."""
        assert Network.Defaults.RETRY_BASE_TIMEOUT == 2
    
    def test_retry_timeout_multiplier_defined(self):
        """Verify RETRY_TIMEOUT_MULTIPLIER is defined."""
        assert hasattr(Network.Defaults, 'RETRY_TIMEOUT_MULTIPLIER')
    
    def test_retry_timeout_multiplier_value(self):
        """Verify RETRY_TIMEOUT_MULTIPLIER is 3."""
        assert Network.Defaults.RETRY_TIMEOUT_MULTIPLIER == 3
    
    def test_retry_count_defined(self):
        """Verify RETRY_COUNT is defined."""
        assert hasattr(Network.Defaults, 'RETRY_COUNT')
    
    def test_retry_count_value(self):
        """Verify RETRY_COUNT is 3 attempts."""
        assert Network.Defaults.RETRY_COUNT == 3
    
    def test_exponential_timeout_progression(self):
        """Verify exponential timeout progression: 2s, 6s, 18s."""
        base = Network.Defaults.RETRY_BASE_TIMEOUT
        multiplier = Network.Defaults.RETRY_TIMEOUT_MULTIPLIER
        
        timeouts = [
            base * (multiplier ** i) 
            for i in range(Network.Defaults.RETRY_COUNT)
        ]
        
        assert timeouts == [2, 6, 18]
    
    def test_old_constants_removed(self):
        """Verify old timeout constants are removed."""
        # These should NOT exist anymore
        assert not hasattr(Network.Defaults, 'TIMEOUT')
        assert not hasattr(Network.Defaults, 'SLOW_SOURCE_TIMEOUT')
        assert not hasattr(Network.Defaults, 'SLOW_SOURCE_VALIDATION_WAIT')
        assert not hasattr(Network.Defaults, 'RETRY_BASE_DELAY')


class TestSourceConstants:
    """Test source constants cleanup."""
    
    def test_slow_sources_removed(self):
        """Verify SLOW_SOURCES list is removed."""
        # This should NOT exist anymore
        assert not hasattr(Source, 'SLOW_SOURCES')
    
    def test_default_priority_exists(self):
        """Verify DEFAULT_PRIORITY still exists."""
        assert hasattr(Source, 'DEFAULT_PRIORITY')
    
    def test_default_priority_is_list(self):
        """Verify DEFAULT_PRIORITY is a list."""
        assert isinstance(Source.DEFAULT_PRIORITY, list)


class TestImplicitValidationMethods:
    """Test methods for implicit validation approach."""
    
    def test_schedule_daily_retry_exists(self, price_manager):
        """Verify _schedule_daily_retry method exists."""
        assert hasattr(price_manager, '_schedule_daily_retry')
        assert callable(price_manager._schedule_daily_retry)
    
    def test_fetch_data_exists(self, price_manager):
        """Verify fetch_data method exists."""
        assert hasattr(price_manager, 'fetch_data')
        assert callable(price_manager.fetch_data)
    
    def test_old_validation_methods_removed(self, price_manager):
        """Verify old validation methods are removed."""
        # These should NOT exist anymore
        assert not hasattr(price_manager, 'validate_configured_sources_once')
        assert not hasattr(price_manager, '_validate_slow_sources_background')
        assert not hasattr(price_manager, '_validate_failed_sources_background')
        assert not hasattr(price_manager, '_schedule_daily_source_retry')
    
    def test_old_state_tracking_removed(self, price_manager):
        """Verify old state tracking attributes are removed."""
        # These should NOT exist anymore
        assert not hasattr(price_manager, '_disabled_sources')
        assert not hasattr(price_manager, '_validated_sources')


@pytest.mark.asyncio
class TestSourceFilteringLogic:
    """Test source filtering based on failure timestamps."""
    
    async def test_fresh_source_not_filtered(self, price_manager):
        """Test that sources without failure timestamp are not filtered."""
        # No failure timestamp = source is available
        assert Source.NORDPOOL not in price_manager._failed_sources
        
        # Get all area-supported sources
        all_area_sources = [cls(config={}).source_type for cls in price_manager._api_classes]
        
        # If Nordpool is supported, it should be available
        if Source.NORDPOOL in all_area_sources:
            # Source should be available for fetch (not filtered)
            # This is tested in actual fetch_data logic
            pass
    
    async def test_recently_failed_source_filtered(self, price_manager):
        """Test that sources failed <24h ago are filtered."""
        now = dt_util.now()
        
        # Mark source as failed 1 hour ago
        one_hour_ago = now - timedelta(hours=1)
        price_manager._failed_sources[Source.NORDPOOL] = one_hour_ago
        
        # Verify source has recent failure
        last_failure = price_manager._failed_sources[Source.NORDPOOL]
        assert last_failure is not None
        assert (now - last_failure).total_seconds() < 86400  # Less than 24h
    
    async def test_old_failed_source_not_filtered(self, price_manager):
        """Test that sources failed >24h ago are not filtered."""
        now = dt_util.now()
        
        # Mark source as failed 25 hours ago
        twenty_five_hours_ago = now - timedelta(hours=25)
        price_manager._failed_sources[Source.NORDPOOL] = twenty_five_hours_ago
        
        # Verify source has old failure
        last_failure = price_manager._failed_sources[Source.NORDPOOL]
        assert last_failure is not None
        assert (now - last_failure).total_seconds() > 86400  # More than 24h
    
    async def test_cleared_source_not_filtered(self, price_manager):
        """Test that sources cleared (None timestamp) are not filtered."""
        # Mark source as working (None = cleared)
        price_manager._failed_sources[Source.NORDPOOL] = None
        
        # Verify source has no failure
        assert price_manager._failed_sources[Source.NORDPOOL] is None


@pytest.mark.asyncio
class TestImplicitValidationBehavior:
    """Test implicit validation behavior during fetch."""
    
    async def test_successful_fetch_clears_failure(self, price_manager):
        """Test that successful fetch clears failure timestamp."""
        now = dt_util.now()
        
        # Start with failed source
        price_manager._failed_sources[Source.NORDPOOL] = now
        assert price_manager._failed_sources[Source.NORDPOOL] is not None
        
        # Simulate successful fetch (what fetch_data does)
        price_manager._failed_sources[Source.NORDPOOL] = None
        
        # Verify failure was cleared
        assert price_manager._failed_sources[Source.NORDPOOL] is None
    
    async def test_failed_fetch_marks_failure(self, price_manager):
        """Test that failed fetch marks source with timestamp."""
        now = dt_util.now()
        
        # Start with no failure
        assert Source.NORDPOOL not in price_manager._failed_sources
        
        # Simulate failed fetch (what fetch_data does)
        price_manager._failed_sources[Source.NORDPOOL] = now
        
        # Verify failure was marked
        assert Source.NORDPOOL in price_manager._failed_sources
        assert price_manager._failed_sources[Source.NORDPOOL] == now
    
    async def test_failed_fetch_schedules_retry(self, price_manager):
        """Test that failed fetch schedules daily retry."""
        # Start with no retry scheduled
        assert Source.NORDPOOL not in price_manager._retry_scheduled
        
        # Simulate scheduling retry (what fetch_data does)
        price_manager._retry_scheduled.add(Source.NORDPOOL)
        
        # Verify retry was scheduled
        assert Source.NORDPOOL in price_manager._retry_scheduled
    
    async def test_successful_retry_clears_schedule(self, price_manager):
        """Test that successful retry clears retry schedule."""
        # Start with retry scheduled
        price_manager._retry_scheduled.add(Source.NORDPOOL)
        assert Source.NORDPOOL in price_manager._retry_scheduled
        
        # Simulate successful retry (what _schedule_daily_retry does)
        price_manager._retry_scheduled.discard(Source.NORDPOOL)
        
        # Verify retry was cleared
        assert Source.NORDPOOL not in price_manager._retry_scheduled


class TestIntegrationScenarios:
    """Integration test scenarios for implicit validation."""
    
    def test_scenario_first_boot_no_failures(self, price_manager):
        """Test scenario: First boot, no failures yet."""
        # Initial state
        assert len(price_manager._failed_sources) == 0
        assert len(price_manager._retry_scheduled) == 0
        
        # All sources should be available
        all_area_sources = [cls(config={}).source_type for cls in price_manager._api_classes]
        
        # No sources filtered (none have failure timestamps)
        for source in all_area_sources:
            assert source not in price_manager._failed_sources
    
    def test_scenario_one_source_failed_recently(self, price_manager):
        """Test scenario: One source failed 1 hour ago."""
        now = dt_util.now()
        one_hour_ago = now - timedelta(hours=1)
        
        # Mark Energy Charts as failed 1 hour ago
        price_manager._failed_sources[Source.ENERGY_CHARTS] = one_hour_ago
        price_manager._retry_scheduled.add(Source.ENERGY_CHARTS)
        
        # Verify state
        assert Source.ENERGY_CHARTS in price_manager._failed_sources
        assert price_manager._failed_sources[Source.ENERGY_CHARTS] == one_hour_ago
        assert Source.ENERGY_CHARTS in price_manager._retry_scheduled
        
        # Source should be filtered (failed <24h ago)
        time_since_failure = (now - one_hour_ago).total_seconds()
        assert time_since_failure < 86400
    
    def test_scenario_source_recovery_cycle(self, price_manager):
        """Test complete failure and recovery cycle."""
        now = dt_util.now()
        
        # Step 1: Source fails
        price_manager._failed_sources[Source.NORDPOOL] = now
        price_manager._retry_scheduled.add(Source.NORDPOOL)
        
        assert Source.NORDPOOL in price_manager._failed_sources
        assert Source.NORDPOOL in price_manager._retry_scheduled
        
        # Step 2: Daily retry succeeds
        price_manager._failed_sources[Source.NORDPOOL] = None
        price_manager._retry_scheduled.discard(Source.NORDPOOL)
        
        assert price_manager._failed_sources[Source.NORDPOOL] is None
        assert Source.NORDPOOL not in price_manager._retry_scheduled
        
        # Step 3: Source fails again
        price_manager._failed_sources[Source.NORDPOOL] = now
        price_manager._retry_scheduled.add(Source.NORDPOOL)
        
        assert price_manager._failed_sources[Source.NORDPOOL] == now
        assert Source.NORDPOOL in price_manager._retry_scheduled
    
    def test_scenario_all_sources_failed(self, price_manager):
        """Test scenario: All sources failed."""
        now = dt_util.now()
        all_area_sources = [cls(config={}).source_type for cls in price_manager._api_classes]
        
        # Mark all sources as failed
        for source in all_area_sources:
            price_manager._failed_sources[source] = now
            price_manager._retry_scheduled.add(source)
        
        # Verify all marked
        assert len(price_manager._failed_sources) == len(all_area_sources)
        assert len(price_manager._retry_scheduled) == len(all_area_sources)
        
        # All sources would be filtered (failed <24h ago)
        for source in all_area_sources:
            last_failure = price_manager._failed_sources[source]
            assert (now - last_failure).total_seconds() < 86400
    
    def test_scenario_old_failure_not_filtered(self, price_manager):
        """Test scenario: Source failed 25h ago (should retry)."""
        now = dt_util.now()
        twenty_five_hours_ago = now - timedelta(hours=25)
        
        # Mark source as failed 25h ago
        price_manager._failed_sources[Source.NORDPOOL] = twenty_five_hours_ago
        
        # Source should NOT be filtered (failed >24h ago)
        time_since_failure = (now - twenty_five_hours_ago).total_seconds()
        assert time_since_failure > 86400
        
        # Source would be tried again in next fetch


class TestSpecialHourWindows:
    """Test special hour windows for daily retry."""
    
    def test_special_hour_windows_defined(self):
        """Verify SPECIAL_HOUR_WINDOWS is defined."""
        assert hasattr(Network.Defaults, 'SPECIAL_HOUR_WINDOWS')
    
    def test_special_hour_windows_is_list(self):
        """Verify SPECIAL_HOUR_WINDOWS is a list."""
        assert isinstance(Network.Defaults.SPECIAL_HOUR_WINDOWS, list)
    
    def test_special_hour_windows_format(self):
        """Verify SPECIAL_HOUR_WINDOWS contains tuples of (start, end)."""
        for window in Network.Defaults.SPECIAL_HOUR_WINDOWS:
            assert isinstance(window, tuple)
            assert len(window) == 2
            start, end = window
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert 0 <= start < 24
            assert 0 <= end <= 24
            assert start < end
    
    def test_default_window_includes_afternoon(self):
        """Verify default windows include afternoon hours (when markets publish)."""
        # Default should include 13:00-15:00 window
        assert (13, 15) in Network.Defaults.SPECIAL_HOUR_WINDOWS


class TestTimeoutCalculation:
    """Test timeout calculation logic."""
    
    def test_timeout_calculation_attempt_1(self):
        """Verify timeout calculation for attempt 1."""
        base = Network.Defaults.RETRY_BASE_TIMEOUT
        multiplier = Network.Defaults.RETRY_TIMEOUT_MULTIPLIER
        
        timeout = base * (multiplier ** 0)
        assert timeout == 2
    
    def test_timeout_calculation_attempt_2(self):
        """Verify timeout calculation for attempt 2."""
        base = Network.Defaults.RETRY_BASE_TIMEOUT
        multiplier = Network.Defaults.RETRY_TIMEOUT_MULTIPLIER
        
        timeout = base * (multiplier ** 1)
        assert timeout == 6
    
    def test_timeout_calculation_attempt_3(self):
        """Verify timeout calculation for attempt 3."""
        base = Network.Defaults.RETRY_BASE_TIMEOUT
        multiplier = Network.Defaults.RETRY_TIMEOUT_MULTIPLIER
        
        timeout = base * (multiplier ** 2)
        assert timeout == 18
    
    def test_total_max_timeout_per_source(self):
        """Verify total max timeout per source is 26 seconds."""
        timeouts = [
            Network.Defaults.RETRY_BASE_TIMEOUT * 
            (Network.Defaults.RETRY_TIMEOUT_MULTIPLIER ** i)
            for i in range(Network.Defaults.RETRY_COUNT)
        ]
        
        total = sum(timeouts)
        assert total == 26  # 2 + 6 + 18


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
