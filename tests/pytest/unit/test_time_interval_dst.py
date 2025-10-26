"""Tests for TimeInterval DST-aware interval counting."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.ge_spot.const.time import TimeInterval


class TestTimeIntervalDSTAware:
    """Test DST-aware interval counting methods."""

    def test_get_expected_intervals_normal_day(self):
        """Test normal day returns 96 intervals."""
        # Use a normal day (not DST transition) in Copenhagen
        normal_date = datetime(
            2025, 10, 1, 12, 0, 0, tzinfo=ZoneInfo("Europe/Copenhagen")
        )

        result = TimeInterval.get_expected_intervals_for_date(
            normal_date, "Europe/Copenhagen"
        )

        assert result == 96, "Normal day should have 96 intervals (24 hours × 4)"

    def test_get_expected_intervals_spring_forward(self):
        """Test spring forward day returns 92 intervals."""
        # DST spring forward in Europe is last Sunday of March
        # In 2025, that's March 30
        spring_date = datetime(
            2025, 3, 30, 12, 0, 0, tzinfo=ZoneInfo("Europe/Copenhagen")
        )

        result = TimeInterval.get_expected_intervals_for_date(
            spring_date, "Europe/Copenhagen"
        )

        assert (
            result == 92
        ), "Spring forward day should have 92 intervals (23 hours × 4)"

    def test_get_expected_intervals_fall_back(self):
        """Test fall back day returns 100 intervals."""
        # DST fall back in Europe is last Sunday of October
        # In 2025, that's October 26
        fall_date = datetime(
            2025, 10, 26, 12, 0, 0, tzinfo=ZoneInfo("Europe/Copenhagen")
        )

        result = TimeInterval.get_expected_intervals_for_date(
            fall_date, "Europe/Copenhagen"
        )

        assert result == 100, "Fall back day should have 100 intervals (25 hours × 4)"

    def test_get_expected_intervals_different_timezone_spring(self):
        """Test spring forward in different timezone (US/Chicago)."""
        # DST spring forward in US is second Sunday of March
        # In 2025, that's March 9
        spring_date = datetime(2025, 3, 9, 12, 0, 0, tzinfo=ZoneInfo("America/Chicago"))

        result = TimeInterval.get_expected_intervals_for_date(
            spring_date, "America/Chicago"
        )

        assert (
            result == 92
        ), "Spring forward day should have 92 intervals in US timezone"

    def test_get_expected_intervals_different_timezone_fall(self):
        """Test fall back in different timezone (US/Chicago)."""
        # DST fall back in US is first Sunday of November
        # In 2025, that's November 2
        fall_date = datetime(2025, 11, 2, 12, 0, 0, tzinfo=ZoneInfo("America/Chicago"))

        result = TimeInterval.get_expected_intervals_for_date(
            fall_date, "America/Chicago"
        )

        assert result == 100, "Fall back day should have 100 intervals in US timezone"

    def test_get_expected_intervals_naive_datetime(self):
        """Test with naive datetime (no timezone info)."""
        # Naive datetime - should still work by using the provided timezone string
        naive_date = datetime(2025, 10, 26, 12, 0, 0)

        result = TimeInterval.get_expected_intervals_for_date(
            naive_date, "Europe/Copenhagen"
        )

        assert (
            result == 100
        ), "Should handle naive datetime by localizing to provided timezone"

    def test_get_expected_intervals_sydney_dst(self):
        """Test DST in Southern Hemisphere (Australia/Sydney)."""
        # DST in Sydney: starts first Sunday of October, ends first Sunday of April
        # In 2025, DST ends on April 6 (fall back, gain 1 hour)
        fall_date = datetime(2025, 4, 6, 12, 0, 0, tzinfo=ZoneInfo("Australia/Sydney"))

        result = TimeInterval.get_expected_intervals_for_date(
            fall_date, "Australia/Sydney"
        )

        assert result == 100, "Fall back day in Sydney should have 100 intervals"

    def test_get_expected_intervals_sydney_spring(self):
        """Test DST spring in Southern Hemisphere (Australia/Sydney)."""
        # DST in Sydney starts October 5, 2025 (spring forward, lose 1 hour)
        spring_date = datetime(
            2025, 10, 5, 12, 0, 0, tzinfo=ZoneInfo("Australia/Sydney")
        )

        result = TimeInterval.get_expected_intervals_for_date(
            spring_date, "Australia/Sydney"
        )

        assert result == 92, "Spring forward day in Sydney should have 92 intervals"

    def test_static_methods_consistency(self):
        """Test that static methods return consistent values."""
        # Verify the base calculations are correct
        assert TimeInterval.get_intervals_per_day() == 96
        assert TimeInterval.get_intervals_per_day_dst_spring() == 92
        assert TimeInterval.get_intervals_per_day_dst_fall() == 100

        # Verify intervals per hour
        assert TimeInterval.get_intervals_per_hour() == 4

        # Verify interval minutes
        assert TimeInterval.get_interval_minutes() == 15
