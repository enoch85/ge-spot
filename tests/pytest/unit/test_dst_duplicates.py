"""Tests for DST fall-back duplicate interval handling in timezone converter."""

import pytest
from datetime import datetime, timezone as tz
from zoneinfo import ZoneInfo
from unittest.mock import Mock, MagicMock

from custom_components.ge_spot.timezone.timezone_converter import TimezoneConverter
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.const.config import Config


class TestDSTFallbackDuplicates:
    """Test DST fall-back duplicate interval handling."""

    def test_dst_fallback_preserves_both_occurrences(self):
        """Test that both occurrences of repeated hour are preserved on DST fall-back day."""
        # Setup: Europe/Stockholm on Oct 26, 2025 (DST fall-back day)
        # At 3:00 AM, clock goes back to 2:00 AM, so 02:00-02:59 happens twice

        # Mock Home Assistant with Stockholm timezone
        mock_hass = MagicMock()
        mock_hass.config.time_zone = "Europe/Stockholm"

        # Create timezone service with Stockholm as both system and area timezone
        tz_service = TimezoneService(hass=mock_hass, area="SE")
        converter = TimezoneConverter(tz_service)

        # Simulate Nordpool providing 25 hours of data (100 intervals) on DST fall-back day
        # Using UTC timestamps to avoid ambiguity
        interval_prices = {}

        # First occurrence of 02:00 hour (still in DST, UTC+2)
        interval_prices["2025-10-26T00:00:00+00:00"] = 10.0  # 02:00 Stockholm (first)
        interval_prices["2025-10-26T00:15:00+00:00"] = 10.1  # 02:15 Stockholm (first)
        interval_prices["2025-10-26T00:30:00+00:00"] = 10.2  # 02:30 Stockholm (first)
        interval_prices["2025-10-26T00:45:00+00:00"] = 10.3  # 02:45 Stockholm (first)

        # Second occurrence of 02:00 hour (after DST ended, UTC+1)
        interval_prices["2025-10-26T01:00:00+00:00"] = 20.0  # 02:00 Stockholm (second)
        interval_prices["2025-10-26T01:15:00+00:00"] = 20.1  # 02:15 Stockholm (second)
        interval_prices["2025-10-26T01:30:00+00:00"] = 20.2  # 02:30 Stockholm (second)
        interval_prices["2025-10-26T01:45:00+00:00"] = 20.3  # 02:45 Stockholm (second)

        # Some other hours for context
        interval_prices["2025-10-26T02:00:00+00:00"] = 30.0  # 03:00 Stockholm

        # Normalize with preserve_date=True
        result = converter.normalize_interval_prices(
            interval_prices, source_timezone_str="UTC", preserve_date=True
        )

        # Should have 9 keys with DST suffixes for the repeated hour
        assert len(result) == 9, f"Expected 9 intervals, got {len(result)}"

        # Check that both occurrences are preserved with suffixes
        assert "2025-10-26 02:00_1" in result, "First 02:00 should have _1 suffix"
        assert "2025-10-26 02:00_2" in result, "Second 02:00 should have _2 suffix"
        assert "2025-10-26 02:15_1" in result
        assert "2025-10-26 02:15_2" in result
        assert "2025-10-26 02:30_1" in result
        assert "2025-10-26 02:30_2" in result
        assert "2025-10-26 02:45_1" in result
        assert "2025-10-26 02:45_2" in result

        # Check values are correct
        assert result["2025-10-26 02:00_1"] == 10.0
        assert result["2025-10-26 02:00_2"] == 20.0
        assert result["2025-10-26 02:15_1"] == 10.1
        assert result["2025-10-26 02:15_2"] == 20.1

    def test_dst_fallback_split_preserves_suffixes(self):
        """Test that DST suffixes are preserved when splitting into today/tomorrow."""
        # Mock Home Assistant with Stockholm timezone
        mock_hass = MagicMock()
        mock_hass.config.time_zone = "Europe/Stockholm"

        tz_service = TimezoneService(hass=mock_hass, area="SE")
        converter = TimezoneConverter(tz_service)

        # Create normalized prices with DST suffixes (as would come from normalize_interval_prices)
        normalized_prices = {
            "2025-10-26 01:00": 5.0,
            "2025-10-26 02:00_1": 10.0,  # First occurrence
            "2025-10-26 02:15_1": 10.1,
            "2025-10-26 02:00_2": 20.0,  # Second occurrence
            "2025-10-26 02:15_2": 20.1,
            "2025-10-26 03:00": 15.0,
            "2025-10-27 00:00": 25.0,  # Tomorrow
        }

        # Mock current time to Oct 26, 2025
        import unittest.mock as mock

        with mock.patch(
            "custom_components.ge_spot.timezone.timezone_converter.datetime"
        ) as mock_datetime:
            mock_now = datetime(
                2025, 10, 26, 10, 0, 0, tzinfo=ZoneInfo("Europe/Stockholm")
            )
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            today, tomorrow = converter.split_into_today_tomorrow(normalized_prices)

        # Today should have all intervals including DST suffixes
        assert (
            len(today) == 6
        ), f"Expected 6 today intervals, got {len(today)}: {list(today.keys())}"
        assert "01:00" in today
        assert "02:00_1" in today
        assert "02:15_1" in today
        assert "02:00_2" in today
        assert "02:15_2" in today
        assert "03:00" in today

        # Tomorrow should have 1 interval
        assert len(tomorrow) == 1
        assert "00:00" in tomorrow

        # Values should be preserved
        assert today["02:00_1"] == 10.0
        assert today["02:00_2"] == 20.0

    def test_normal_day_no_suffixes(self):
        """Test that normal days (non-DST) don't get suffixes."""
        # Mock Home Assistant with Stockholm timezone
        mock_hass = MagicMock()
        mock_hass.config.time_zone = "Europe/Stockholm"

        tz_service = TimezoneService(hass=mock_hass, area="SE")
        converter = TimezoneConverter(tz_service)

        # Normal day - no duplicates
        interval_prices = {
            "2025-10-25T00:00:00+00:00": 10.0,  # 02:00 Stockholm
            "2025-10-25T00:15:00+00:00": 10.1,  # 02:15 Stockholm
            "2025-10-25T01:00:00+00:00": 20.0,  # 03:00 Stockholm
        }

        result = converter.normalize_interval_prices(
            interval_prices, source_timezone_str="UTC", preserve_date=True
        )

        # Should have no suffixes on normal day
        assert "2025-10-25 02:00" in result
        assert "2025-10-25 02:15" in result
        assert "2025-10-25 03:00" in result

        # Should NOT have suffixes
        assert "2025-10-25 02:00_1" not in result
        assert "2025-10-25 02:00_2" not in result

    def test_dst_spring_forward_no_duplicates(self):
        """Test that DST spring-forward day has no duplicates (hour is skipped)."""
        # Mock Home Assistant with Stockholm timezone
        mock_hass = MagicMock()
        mock_hass.config.time_zone = "Europe/Stockholm"

        tz_service = TimezoneService(hass=mock_hass, area="SE")
        converter = TimezoneConverter(tz_service)

        # Spring forward: 2:00 AM jumps to 3:00 AM, so no 02:00-02:59
        interval_prices = {
            "2025-03-30T00:00:00+00:00": 10.0,  # 01:00 Stockholm (before spring forward)
            "2025-03-30T01:00:00+00:00": 30.0,  # 03:00 Stockholm (after spring forward, 02:00 doesn't exist)
            "2025-03-30T02:00:00+00:00": 40.0,  # 04:00 Stockholm
        }

        result = converter.normalize_interval_prices(
            interval_prices, source_timezone_str="UTC", preserve_date=True
        )

        # Should have no duplicates
        assert len(result) == 3
        assert "2025-03-30 01:00" in result
        assert "2025-03-30 03:00" in result  # 02:00 is skipped
        assert "2025-03-30 04:00" in result

        # Should NOT have 02:00 at all
        assert "2025-03-30 02:00" not in result
