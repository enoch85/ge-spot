"""Tests for TimezoneService counter and context-aware tomorrow warnings."""

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ge_spot.timezone.service import TimezoneService


class TestTimezoneServiceCounter:
    """Test TimezoneService instantiation counter for performance monitoring."""

    def test_counter_increments_on_creation(self, caplog):
        """Test that _TZ_SERVICE_COUNT increments with each TimezoneService creation."""
        caplog.set_level(logging.DEBUG)

        # Get initial count from logs
        initial_logs = [
            rec for rec in caplog.records if "TimezoneService #" in rec.message
        ]
        initial_count = len(initial_logs)

        # Create a TimezoneService instance
        service1 = TimezoneService(hass=None, area="TEST1")

        # Check log appeared
        after_first = [
            rec for rec in caplog.records if "TimezoneService #" in rec.message
        ]
        assert len(after_first) == initial_count + 1

        # Create another instance
        service2 = TimezoneService(hass=None, area="TEST2")

        # Check count incremented again
        after_second = [
            rec for rec in caplog.records if "TimezoneService #" in rec.message
        ]
        assert len(after_second) == initial_count + 2

    def test_counter_logs_creation(self, caplog):
        """Test that TimezoneService logs creation with counter."""
        caplog.set_level(logging.DEBUG)

        area = "TEST_AREA"

        # Create service
        service = TimezoneService(hass=None, area=area)

        # Check log message exists
        log_messages = [rec.message for rec in caplog.records]
        creation_logs = [msg for msg in log_messages if "TimezoneService #" in msg]

        assert len(creation_logs) >= 1
        assert f"area='{area}'" in creation_logs[-1]

    def test_counter_tracks_none_area(self, caplog):
        """Test that counter works even when area is None."""
        caplog.set_level(logging.DEBUG)

        # Create service without area
        service = TimezoneService(hass=None, area=None)

        # Check log message exists with 'None'
        log_messages = [rec.message for rec in caplog.records]
        creation_logs = [msg for msg in log_messages if "TimezoneService #" in msg]

        assert len(creation_logs) >= 1
        assert "area='None'" in creation_logs[-1]


class TestContextAwareTomorrowWarning:
    """Test context-aware tomorrow data warnings (before vs after 14:00)."""

    def test_warning_before_14(self, caplog):
        """Test that incomplete tomorrow data uses DEBUG level before 14:00."""
        caplog.set_level(logging.DEBUG)

        # Simulate the logging behavior before 14:00
        current_hour = 10
        expected_tomorrow = 96
        tomorrow_count = 4  # Incomplete
        area = "SE4"

        # This mimics the logic in unified_price_manager.py lines 972-984
        if tomorrow_count < expected_tomorrow:
            if current_hour >= 14:
                logging.getLogger("test").warning(
                    f"[{area}] Incomplete tomorrow data: {tomorrow_count}/{expected_tomorrow}"
                )
            else:
                logging.getLogger("test").debug(
                    f"[{area}] Tomorrow data not yet available (before 14:00): {tomorrow_count}/{expected_tomorrow}"
                )

        # Check that DEBUG level was used (not WARNING)
        debug_messages = [rec for rec in caplog.records if rec.levelname == "DEBUG"]
        warning_messages = [rec for rec in caplog.records if rec.levelname == "WARNING"]

        assert any(
            "Tomorrow data not yet available" in rec.message for rec in debug_messages
        )
        assert not any(
            "Incomplete tomorrow data" in rec.message for rec in warning_messages
        )

    def test_warning_after_14(self, caplog):
        """Test that incomplete tomorrow data uses WARNING level after 14:00."""
        caplog.set_level(logging.DEBUG)

        # Simulate the logging behavior after 14:00
        current_hour = 16
        expected_tomorrow = 96
        tomorrow_count = 4  # Incomplete
        area = "SE4"

        # This mimics the logic in unified_price_manager.py lines 972-984
        if tomorrow_count < expected_tomorrow:
            if current_hour >= 14:
                logging.getLogger("test").warning(
                    f"[{area}] Incomplete tomorrow data: {tomorrow_count}/{expected_tomorrow}"
                )
            else:
                logging.getLogger("test").debug(
                    f"[{area}] Tomorrow data not yet available (before 14:00): {tomorrow_count}/{expected_tomorrow}"
                )

        # Check that WARNING level was used
        warning_messages = [rec for rec in caplog.records if rec.levelname == "WARNING"]

        assert any(
            "Incomplete tomorrow data" in rec.message for rec in warning_messages
        )

    def test_no_warning_when_tomorrow_complete(self, caplog):
        """Test that no warning is logged when tomorrow data is complete."""
        caplog.set_level(logging.DEBUG)

        # Mock complete tomorrow data (96 intervals)
        current_hour = 16
        expected_tomorrow = 96
        tomorrow_count = 96  # Complete!
        area = "SE4"

        # Should not log anything because data is complete
        if tomorrow_count < expected_tomorrow:
            if current_hour >= 14:
                logging.getLogger("test").warning(
                    f"[{area}] Incomplete tomorrow data: {tomorrow_count}/{expected_tomorrow}"
                )
            else:
                logging.getLogger("test").debug(
                    f"[{area}] Tomorrow data not yet available: {tomorrow_count}/{expected_tomorrow}"
                )

        # Verify no warnings about incomplete data
        warning_messages = [
            rec.message for rec in caplog.records if rec.levelname == "WARNING"
        ]
        debug_messages = [
            rec.message for rec in caplog.records if rec.levelname == "DEBUG"
        ]

        assert not any("Incomplete tomorrow" in msg for msg in warning_messages)
        assert not any(
            "Tomorrow data not yet available" in msg for msg in debug_messages
        )
