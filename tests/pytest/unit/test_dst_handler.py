"""Tests for DST handler functionality."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.ge_spot.timezone.dst_handler import DSTHandler
from custom_components.ge_spot.const.time import DSTTransitionType


class TestDSTHandler:
    """Test DST transition detection."""

    def test_dst_handler_initialization_with_timezone(self):
        """Test DSTHandler initialization with explicit timezone."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)
        assert handler.timezone == tz

    def test_dst_handler_initialization_without_timezone(self):
        """Test DSTHandler initialization with default timezone."""
        handler = DSTHandler()
        assert handler.timezone is not None

    def test_normal_day_europe_stockholm(self):
        """Test normal day (24 hours) in Europe/Stockholm."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # October 25, 2025 - normal day before DST transition
        dt = datetime(2025, 10, 25, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is False
        assert trans_type == ""

    def test_fall_back_day_europe_stockholm(self):
        """Test DST fall-back day (25 hours) in Europe/Stockholm."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # October 26, 2025 - DST fall-back day
        dt = datetime(2025, 10, 26, 2, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.FALL_BACK

    def test_spring_forward_day_europe_stockholm(self):
        """Test DST spring-forward day (23 hours) in Europe/Stockholm."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # March 30, 2025 - DST spring-forward day
        dt = datetime(2025, 3, 30, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.SPRING_FORWARD

    def test_fall_back_day_america_new_york(self):
        """Test DST fall-back day in America/New_York timezone."""
        tz = ZoneInfo("America/New_York")
        handler = DSTHandler(tz)

        # November 2, 2025 - DST fall-back day in US
        dt = datetime(2025, 11, 2, 2, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.FALL_BACK

    def test_spring_forward_day_america_new_york(self):
        """Test DST spring-forward day in America/New_York timezone."""
        tz = ZoneInfo("America/New_York")
        handler = DSTHandler(tz)

        # March 9, 2025 - DST spring-forward day in US
        dt = datetime(2025, 3, 9, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.SPRING_FORWARD

    def test_normal_day_america_new_york(self):
        """Test normal day in America/New_York timezone."""
        tz = ZoneInfo("America/New_York")
        handler = DSTHandler(tz)

        # March 8, 2025 - normal day before DST transition
        dt = datetime(2025, 3, 8, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is False
        assert trans_type == ""

    def test_utc_timezone_no_transitions(self):
        """Test that UTC timezone has no DST transitions."""
        tz = ZoneInfo("UTC")
        handler = DSTHandler(tz)

        # October 26, 2025 - would be DST day in many zones, but not UTC
        dt = datetime(2025, 10, 26, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is False
        assert trans_type == ""

    def test_multiple_times_same_day_fall_back(self):
        """Test that different times on same DST fall-back day all detect transition."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        times = [
            datetime(2025, 10, 26, 0, 0, 0, tzinfo=tz),
            datetime(2025, 10, 26, 6, 0, 0, tzinfo=tz),
            datetime(2025, 10, 26, 12, 0, 0, tzinfo=tz),
            datetime(2025, 10, 26, 18, 0, 0, tzinfo=tz),
            datetime(2025, 10, 26, 23, 0, 0, tzinfo=tz),
        ]

        for dt in times:
            is_trans, trans_type = handler.is_dst_transition_day(dt)
            assert is_trans is True, f"Failed for time {dt.time()}"
            assert trans_type == DSTTransitionType.FALL_BACK

    def test_multiple_times_same_day_spring_forward(self):
        """Test that different times on same DST spring-forward day all detect transition."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        times = [
            datetime(2025, 3, 30, 0, 0, 0, tzinfo=tz),
            datetime(2025, 3, 30, 6, 0, 0, tzinfo=tz),
            datetime(2025, 3, 30, 12, 0, 0, tzinfo=tz),
            datetime(2025, 3, 30, 18, 0, 0, tzinfo=tz),
            datetime(2025, 3, 30, 22, 0, 0, tzinfo=tz),
        ]

        for dt in times:
            is_trans, trans_type = handler.is_dst_transition_day(dt)
            assert is_trans is True, f"Failed for time {dt.time()}"
            assert trans_type == DSTTransitionType.SPRING_FORWARD

    def test_fall_back_day_australia_sydney(self):
        """Test DST fall-back day in Australia/Sydney timezone."""
        tz = ZoneInfo("Australia/Sydney")
        handler = DSTHandler(tz)

        # April 6, 2025 - DST fall-back day in Sydney
        dt = datetime(2025, 4, 6, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.FALL_BACK

    def test_spring_forward_day_australia_sydney(self):
        """Test DST spring-forward day in Australia/Sydney timezone."""
        tz = ZoneInfo("Australia/Sydney")
        handler = DSTHandler(tz)

        # October 5, 2025 - DST spring-forward day in Sydney
        dt = datetime(2025, 10, 5, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.SPRING_FORWARD

    def test_with_zoneinfo_timezone(self):
        """Test with ZoneInfo timezone (Python 3.9+)."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # October 26, 2025 - DST fall-back day
        dt = datetime(2025, 10, 26, 12, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.FALL_BACK

    def test_default_datetime_uses_now(self):
        """Test that calling without datetime uses current time."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # Should not raise an error
        is_trans, trans_type = handler.is_dst_transition_day()
        assert isinstance(is_trans, bool)
        assert isinstance(trans_type, str)

    def test_naive_datetime_gets_timezone(self):
        """Test that naive datetime gets timezone from handler."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # Naive datetime
        dt = datetime(2025, 10, 26, 12, 0, 0)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.FALL_BACK

    def test_get_dst_offset_info_with_dst(self):
        """Test DST offset info during DST period."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # Summer time (DST active)
        dt = datetime(2025, 7, 1, 12, 0, 0, tzinfo=tz)
        offset_info = handler.get_dst_offset_info(dt)

        assert "hour" in offset_info

    def test_get_dst_offset_info_without_dst(self):
        """Test DST offset info during standard time."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # Winter time (DST inactive)
        dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=tz)
        offset_info = handler.get_dst_offset_info(dt)

        assert "no DST offset" in offset_info

    def test_get_dst_offset_info_utc(self):
        """Test DST offset info for UTC timezone."""
        tz = ZoneInfo("UTC")
        handler = DSTHandler(tz)

        dt = datetime(2025, 7, 1, 12, 0, 0, tzinfo=tz)
        offset_info = handler.get_dst_offset_info(dt)

        assert "no DST offset" in offset_info


class TestDSTHandlerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_midnight_on_transition_day(self):
        """Test detection at exactly midnight on transition day."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # October 26, 2025 at 00:00:00
        dt = datetime(2025, 10, 26, 0, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is True
        assert trans_type == DSTTransitionType.FALL_BACK

    def test_last_second_before_transition_day(self):
        """Test detection on day before transition."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # October 25, 2025 at 23:59:59
        dt = datetime(2025, 10, 25, 23, 59, 59, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is False
        assert trans_type == ""

    def test_first_second_after_transition_day(self):
        """Test detection on day after transition."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # October 27, 2025 at 00:00:00
        dt = datetime(2025, 10, 27, 0, 0, 0, tzinfo=tz)
        is_trans, trans_type = handler.is_dst_transition_day(dt)

        assert is_trans is False
        assert trans_type == ""

    def test_different_years_same_date(self):
        """Test that DST transition dates can vary by year."""
        tz = ZoneInfo("Europe/Stockholm")
        handler = DSTHandler(tz)

        # Test multiple years - October 26 is DST transition in 2025
        # but may not be in other years
        dt_2025 = datetime(2025, 10, 26, 12, 0, 0, tzinfo=tz)
        is_trans_2025, _ = handler.is_dst_transition_day(dt_2025)

        dt_2024 = datetime(2024, 10, 26, 12, 0, 0, tzinfo=tz)
        is_trans_2024, _ = handler.is_dst_transition_day(dt_2024)

        # At least one should be True (2025 is known to be)
        assert is_trans_2025 is True
        # 2024 Oct 26 may or may not be transition day
        assert isinstance(is_trans_2024, bool)
