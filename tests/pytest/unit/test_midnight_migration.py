"""Test midnight migration cache validity recalculation (Issue #44)."""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch, MagicMock
from zoneinfo import ZoneInfo

from custom_components.ge_spot.coordinator.cache_manager import CacheManager
from custom_components.ge_spot.coordinator.data_validity import (
    DataValidity,
    calculate_data_validity,
)
from custom_components.ge_spot.api.base.data_structure import PriceStatistics


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.config = Mock()
    hass.config.time_zone = "Europe/Stockholm"
    return hass


@pytest.fixture
def mock_timezone_service():
    """Create a mock timezone service."""
    tz_service = Mock()
    tz_service.target_timezone = ZoneInfo("Europe/Stockholm")
    tz_service.get_current_interval_key.return_value = "00:00"
    return tz_service


@pytest.fixture
def cache_manager_with_tz(mock_hass, mock_timezone_service):
    """Create a cache manager with timezone service."""
    config = {"cache_ttl": 60}
    cache_mgr = CacheManager(hass=mock_hass, config=config)
    cache_mgr._timezone_service = mock_timezone_service
    return cache_mgr


@pytest.fixture
def yesterday_cache_data():
    """Create cache data representing yesterday's data with tomorrow prices."""
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today()  # Yesterday's tomorrow is today

    # Create 96 intervals for tomorrow (which becomes today after midnight)
    tomorrow_prices = {
        f"{h:02d}:{m:02d}": 100.0 + h for h in range(24) for m in [0, 15, 30, 45]
    }
    tomorrow_raw = {
        f"{h:02d}:{m:02d}": 90.0 + h for h in range(24) for m in [0, 15, 30, 45]
    }

    # Old validity claiming tomorrow=96 (THIS IS THE BUG)
    old_validity = DataValidity(
        interval_count=192,
        today_interval_count=96,
        tomorrow_interval_count=96,  # Wrong after migration!
        has_current_interval=True,
        has_minimum_data=True,
        data_valid_until=datetime.combine(tomorrow, datetime.max.time()),
    )

    # Create tomorrow statistics manually
    tomorrow_stats = {
        "avg": 110.5,
        "min": 100.0,
        "max": 123.0,
        "min_timestamp": None,
        "max_timestamp": None,
    }

    return {
        "area": "SE2",
        "source": "nordpool",
        "today_interval_prices": {
            f"{h:02d}:{m:02d}": 50.0 + h for h in range(24) for m in [0, 15, 30, 45]
        },
        "tomorrow_interval_prices": tomorrow_prices,
        "today_raw_prices": {
            f"{h:02d}:{m:02d}": 40.0 + h for h in range(24) for m in [0, 15, 30, 45]
        },
        "tomorrow_raw_prices": tomorrow_raw,
        "statistics": PriceStatistics().to_dict(),
        "tomorrow_statistics": tomorrow_stats,
        "data_validity": old_validity.to_dict(),
        "source_currency": "EUR",
        "target_currency": "SEK",
    }


class TestMidnightMigration:
    """Test cases for midnight migration validity recalculation."""

    def test_migration_recalculates_validity(
        self, cache_manager_with_tz, yesterday_cache_data, mock_timezone_service
    ):
        """Test that midnight migration recalculates data_validity correctly."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()

        # Create timezone-aware timestamp
        tz = ZoneInfo("Europe/Stockholm")
        timestamp_aware = datetime.now(tz=tz)

        # Store yesterday's cache with tomorrow prices
        cache_manager_with_tz.store(
            area="SE2",
            source="nordpool",
            data=yesterday_cache_data,
            timestamp=timestamp_aware,
            target_date=yesterday,
        )

        # Simulate getting data at 00:05 (within migration window)
        with patch(
            "custom_components.ge_spot.coordinator.cache_manager.dt_util"
        ) as mock_dt:
            # Mock time to be 00:05
            mock_now = datetime.now(tz=tz).replace(
                hour=0, minute=5, second=0, microsecond=0
            )
            mock_dt.now.return_value = mock_now

            # Get data for today (should trigger migration)
            migrated_data = cache_manager_with_tz.get_data(
                area="SE2", target_date=today
            )

        # Verify migration occurred
        assert migrated_data is not None
        assert migrated_data.get("migrated_from_tomorrow") is True
        assert len(migrated_data["today_interval_prices"]) == 96
        assert len(migrated_data["tomorrow_interval_prices"]) == 0

        # CRITICAL: Verify data_validity was recalculated
        assert "data_validity" in migrated_data
        validity = DataValidity.from_dict(migrated_data["data_validity"])

        # Key assertions - validity should reflect actual data
        assert (
            validity.tomorrow_interval_count == 0
        ), "Tomorrow count should be 0 after migration"
        assert (
            validity.today_interval_count == 96
        ), "Today count should be 96 (migrated from tomorrow)"
        assert validity.interval_count == 96, "Total intervals should be 96 (not 192!)"

    def test_migration_moves_raw_prices(
        self, cache_manager_with_tz, yesterday_cache_data
    ):
        """Test that migration also moves tomorrow_raw_prices to today_raw_prices."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        tz = ZoneInfo("Europe/Stockholm")

        cache_manager_with_tz.store(
            area="SE2",
            source="nordpool",
            data=yesterday_cache_data,
            timestamp=datetime.now(tz=tz),
            target_date=yesterday,
        )

        with patch(
            "custom_components.ge_spot.coordinator.cache_manager.dt_util"
        ) as mock_dt:
            mock_now = datetime.now(tz=tz).replace(hour=0, minute=5)
            mock_dt.now.return_value = mock_now
            migrated_data = cache_manager_with_tz.get_data(
                area="SE2", target_date=today
            )

        assert migrated_data is not None
        assert len(migrated_data["today_raw_prices"]) == 96
        assert len(migrated_data["tomorrow_raw_prices"]) == 0
        # Verify raw prices were moved correctly
        assert migrated_data["today_raw_prices"]["00:00"] == 90.0

    def test_migration_clears_tomorrow_statistics(
        self, cache_manager_with_tz, yesterday_cache_data
    ):
        """Test that migration clears tomorrow_statistics."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        tz = ZoneInfo("Europe/Stockholm")

        cache_manager_with_tz.store(
            area="SE2",
            source="nordpool",
            data=yesterday_cache_data,
            timestamp=datetime.now(tz=tz),
            target_date=yesterday,
        )

        with patch(
            "custom_components.ge_spot.coordinator.cache_manager.dt_util"
        ) as mock_dt:
            mock_now = datetime.now(tz=tz).replace(hour=0, minute=5)
            mock_dt.now.return_value = mock_now
            migrated_data = cache_manager_with_tz.get_data(
                area="SE2", target_date=today
            )

        assert migrated_data is not None
        tomorrow_stats = migrated_data.get("tomorrow_statistics", {})
        # Should be empty statistics (all None or 0)
        assert tomorrow_stats.get("avg") is None or tomorrow_stats.get("avg") == 0
        assert tomorrow_stats.get("min") is None or tomorrow_stats.get("min") == 0

    def test_migration_only_in_window(
        self, cache_manager_with_tz, yesterday_cache_data
    ):
        """Test that migration only happens between 00:00-00:10."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        tz = ZoneInfo("Europe/Stockholm")

        cache_manager_with_tz.store(
            area="SE2",
            source="nordpool",
            data=yesterday_cache_data,
            timestamp=datetime.now(tz=tz),
            target_date=yesterday,
        )

        # Try at 00:15 (outside migration window)
        with patch(
            "custom_components.ge_spot.coordinator.cache_manager.dt_util"
        ) as mock_dt:
            mock_now = datetime.now(tz=tz).replace(hour=0, minute=15)
            mock_dt.now.return_value = mock_now
            data = cache_manager_with_tz.get_data(area="SE2", target_date=today)

        # Should NOT migrate (outside window)
        assert data is None or data.get("migrated_from_tomorrow") is not True

    def test_migration_without_timezone_service(self, mock_hass, yesterday_cache_data):
        """Test migration without timezone service removes stale validity."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        tz = ZoneInfo("Europe/Stockholm")

        # Create cache manager WITHOUT timezone service
        config = {"cache_ttl": 60}
        cache_mgr = CacheManager(hass=mock_hass, config=config)
        # Don't set _timezone_service

        cache_mgr.store(
            area="SE2",
            source="nordpool",
            data=yesterday_cache_data,
            timestamp=datetime.now(tz=tz),
            target_date=yesterday,
        )

        with patch(
            "custom_components.ge_spot.coordinator.cache_manager.dt_util"
        ) as mock_dt:
            mock_now = datetime.now(tz=tz).replace(hour=0, minute=5)
            mock_dt.now.return_value = mock_now
            migrated_data = cache_mgr.get_data(area="SE2", target_date=today)

        assert migrated_data is not None
        # Without timezone service, should remove stale validity
        # to force recalculation downstream
        assert (
            "data_validity" not in migrated_data or migrated_data["data_validity"] == {}
        )

    def test_validity_matches_interval_counts(
        self, cache_manager_with_tz, yesterday_cache_data, mock_timezone_service
    ):
        """Test that validity interval counts match actual interval dict lengths."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        tz = ZoneInfo("Europe/Stockholm")

        cache_manager_with_tz.store(
            area="SE2",
            source="nordpool",
            data=yesterday_cache_data,
            timestamp=datetime.now(tz=tz),
            target_date=yesterday,
        )

        with patch(
            "custom_components.ge_spot.coordinator.cache_manager.dt_util"
        ) as mock_dt:
            mock_now = datetime.now(tz=tz).replace(hour=0, minute=5)
            mock_dt.now.return_value = mock_now
            migrated_data = cache_manager_with_tz.get_data(
                area="SE2", target_date=today
            )

        assert migrated_data is not None

        # Get actual interval counts from data
        today_count = len(migrated_data["today_interval_prices"])
        tomorrow_count = len(migrated_data["tomorrow_interval_prices"])

        # Get validity counts
        validity = DataValidity.from_dict(migrated_data["data_validity"])

        # They MUST match
        assert validity.today_interval_count == today_count, (
            f"Validity today count ({validity.today_interval_count}) "
            f"doesn't match actual data ({today_count})"
        )
        assert validity.tomorrow_interval_count == tomorrow_count, (
            f"Validity tomorrow count ({validity.tomorrow_interval_count}) "
            f"doesn't match actual data ({tomorrow_count})"
        )
        assert validity.interval_count == today_count + tomorrow_count, (
            f"Validity total count ({validity.interval_count}) "
            f"doesn't match sum of actual data ({today_count + tomorrow_count})"
        )


class TestMigrationIntegration:
    """Integration tests for migration behavior with unified price manager."""

    @pytest.mark.asyncio
    async def test_fetch_decision_after_migration(
        self, cache_manager_with_tz, yesterday_cache_data, mock_timezone_service
    ):
        """Test that fetch decision uses correct validity after migration."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        tz = ZoneInfo("Europe/Stockholm")

        # Store yesterday's data
        cache_manager_with_tz.store(
            area="SE2",
            source="nordpool",
            data=yesterday_cache_data,
            timestamp=datetime.now(tz=tz),
            target_date=yesterday,
        )

        # Trigger migration at 00:05
        with patch(
            "custom_components.ge_spot.coordinator.cache_manager.dt_util"
        ) as mock_dt:
            mock_now = datetime.now(tz=tz).replace(hour=0, minute=5)
            mock_dt.now.return_value = mock_now
            migrated_data = cache_manager_with_tz.get_data(
                area="SE2", target_date=today
            )

        assert migrated_data is not None, "Migration should have occurred"

        # Verify the migrated data has correct validity
        validity = DataValidity.from_dict(migrated_data["data_validity"])

        # Key check: System should know it needs to fetch tomorrow data
        assert validity.tomorrow_interval_count == 0
        assert not validity.has_minimum_data or validity.interval_count < 192

        # This ensures fetch decision will correctly identify missing tomorrow data
        # and trigger a fetch after 13:00 when tomorrow prices are published


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
